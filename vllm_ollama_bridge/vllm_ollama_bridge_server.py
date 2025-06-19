# ===============================================================
# vllm_ollama_bridge_server.py
# CMD: uvicorn vllm_ollama_bridge.vllm_ollama_bridge_server:app --reload --port 11434
# ===============================================================

# --- 라이브러리 임포트 ---
from fastapi import FastAPI, Request, Response  # 웹 서버 구성 및 요청 객체
from fastapi.responses import JSONResponse, StreamingResponse  # 다양한 HTTP 응답 형식
from pydantic import BaseModel  # 요청/응답 데이터 구조 정의용
import httpx  # 비동기 HTTP 클라이언트
import time  # 시간 측정용
import json  # JSON 처리
import asyncio  # 비동기 처리
from datetime import datetime, timezone  # 시간 및 타임존 처리

# --- FastAPI 애플리케이션 인스턴스 생성 ---
app = FastAPI()

# --- vLLM 서버의 API URL 정의 ---
VLLM_MODELS_URL = "http://vllm_server:8000/v1/models"  # 모델 목록 조회
VLLM_API_URL = "http://vllm_server:8000/v1/chat/completions"  # 채팅 API

# --- 모델 로딩 시간의 기본 추정치 (나노초) ---
# 20GB 모델을 5GB/s 속도로 로딩한다고 가정 → 약 4초
ESTIMATED_MODEL_LOAD_DURATION_NS = 4_000_000_000

# --- 모델별 실제 로딩 시간 기록용 딕셔너리 ---
model_load_durations = {}





# ===============================================================
# 기본 Echo 응답
# ===============================================================
@app.get("/")
async def index():
    return "Ollama is running"





# ===============================================================
# 요청/응답을 모두 로깅하는 HTTP 미들웨어
# ===============================================================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    req_body = await request.body()
    print(f"\n--- REQUEST {request.method} {request.url.path} ---")
    if req_body:
        try:
            print(json.dumps(json.loads(req_body), indent=2, ensure_ascii=False))
        except Exception:
            print(req_body.decode(errors="replace"))
    else:
        print("(no body)")

    response = await call_next(request)

    # 응답 본문은 스트리밍이므로 여기선 출력 안 함
    print(f"--- RESPONSE status_code={response.status_code} media_type={response.media_type} ---")
    return response





# ===============================================================
# 요청 데이터 구조 정의 (Pydantic 모델)
# ===============================================================
class OllamaMessage(BaseModel):
    role: str  # 'user' 또는 'assistant'
    content: str  # 메시지 본문

class OllamaChatRequest(BaseModel):
    model: str  # 사용할 모델 ID
    messages: list[OllamaMessage]  # 채팅 메시지 리스트
    stream: bool = False  # 스트리밍 여부
    options: dict = {}  # 온도 등 기타 옵션





# ===============================================================
# 현재 시간을 Ollama 형식으로 ISO 타임스탬프 반환
# ===============================================================
def get_current_ollama_created_at_format():
    current_time = datetime.now(timezone.utc)
    return current_time.isoformat() + "Z"





# ===============================================================
# 모델 용량 기반으로 로딩 시간 추정 (현재는 고정값만 반환)
# ===============================================================
def estimate_load_duration(model_size_in_vllm_unit):
    return ESTIMATED_MODEL_LOAD_DURATION_NS





# ===============================================================
# vLLM 모델 정보를 Ollama 형식의 모델 태그 정보로 변환
# ===============================================================
def vllm_model_to_ollama_tag(model):
    model_id = model.get("id", "unknown")
    created_at_unix = int(time.time())
    if model.get("created") is not None:
        try:
            created_at_unix = int(model["created"])
        except (ValueError, TypeError):
            pass
    digest = ""
    if model.get("permission") and len(model["permission"]) > 0:
        digest = f"sha256:{model['permission'][0]['id']}"
    size = model.get("max_model_len", 7000000000)

    # 모델 로딩 시간 추정값 저장
    if model_id not in model_load_durations:
        model_load_durations[model_id] = estimate_load_duration(size)
        print(f"--- Model '{model_id}' load_duration estimated and stored: {model_load_durations[model_id]} ns ---")

    return {
        "name": model_id,
        "model": model_id,
        "tag": "latest",
        "digest": digest,
        "size": size,
        "modified_at": created_at_unix,
    }





# ===============================================================
# 모델 목록 조회 API (/api/tags)
# → Ollama가 요구하는 모델 리스트 반환
# ===============================================================
@app.get("/api/tags")
async def list_tags():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(VLLM_MODELS_URL)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            ollama_models = [vllm_model_to_ollama_tag(m) for m in models]
            return Response(
                content=json.dumps({"models": ollama_models}, ensure_ascii=False, separators=(",", ":")),
                media_type="application/json"
            )
        except httpx.RequestError as exc:
            print(f"--- VLLM 모델 목록 가져오기 실패: {exc} ---")
            return Response(
                content=json.dumps({"error": f"VLLM 모델 서버에 연결할 수 없음: {exc}"}, ensure_ascii=False, separators=(",", ":")),
                status_code=500,
                media_type="application/json"
            )
        except Exception as exc:
            print(f"--- VLLM 모델 목록 처리 중 오류: {exc} ---")
            return Response(
                content=json.dumps({"error": f"VLLM 모델 목록 처리 중 오류 발생: {exc}"}, ensure_ascii=False, separators=(",", ":")),
                status_code=500,
                media_type="application/json"
            )





# ===============================================================
# 채팅 요청 처리 API (/api/chat)
# → Ollama에서 채팅 요청을 보내면 이를 vLLM에 전달 후 응답 포맷을 변경
# ===============================================================
@app.post("/api/chat")
async def ollama_chat(request: Request):
    body = await request.json()
    requested_model = body.get("model")
    if not requested_model:
        # 모델 이름 누락 시 오류 반환
        return Response(
            content=json.dumps({
                "model": "error",
                "created_at": get_current_ollama_created_at_format(),
                "message": {
                    "role": "assistant",
                    "content": "⚠️ 모델 이름 누락: 요청에 model 이름이 없음"
                },
                "done": True
            }, ensure_ascii=False, separators=(",", ":")),
            status_code=400,
            media_type="application/json"
        )

    # 모델별 로딩 시간 추정치 조회
    current_model_load_duration = model_load_durations.get(requested_model, ESTIMATED_MODEL_LOAD_DURATION_NS)

    # OpenAI API 형식으로 변환
    openai_payload = {
        "model": requested_model,
        "messages": body["messages"],
        "temperature": body.get("options", {}).get("temperature", 0.7),
        "stream": body.get("stream", False),
    }

    start_time = time.time()
    estimated_prompt_tokens = sum(len(m.get("content", "")) for m in body["messages"])

    # 스트리밍 응답 처리
    if openai_payload["stream"]:
        # 비동기 제너레이터로 스트리밍 구현
        async def stream_vllm():

            # 다양한 응답 메타데이터 변수 초기화
            accumulated_content = ""
            get_current_ollama_created_at_format()
            final_done_reason = None
            final_prompt_eval_count = estimated_prompt_tokens
            final_eval_count = 0
            first_chunk_time = None

            async with httpx.AsyncClient(timeout=None) as client:
                try:
                    async with client.stream("POST", VLLM_API_URL, json=openai_payload) as vllm_resp:
                        vllm_resp.raise_for_status()
                        async for line in vllm_resp.aiter_lines():
                            current_log_time = datetime.now(timezone.utc).isoformat(timespec='microseconds')
                            print(f"[{current_log_time}][vLLM Raw Line]: {line}")

                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                line = line[len("data: "):]
                            if line == "[DONE]":
                                continue

                            try:
                                chunk = json.loads(line)
                            except Exception as e:
                                print(f"[stream parse error] {e} / 원본: {line}")
                                continue

                            # 청크 처리
                            if "choices" in chunk and chunk["choices"]:
                                if first_chunk_time is None:
                                    first_chunk_time = time.time()

                                choice = chunk["choices"][0]
                                content = choice.get("delta", {}).get("content", "")
                                finish_reason = choice.get("finish_reason")
                                done = bool(finish_reason is not None)

                                # 응답 시간 포맷
                                created_at_str = get_current_ollama_created_at_format()
                                if "created" in chunk:
                                    try:
                                        dt_obj = datetime.fromtimestamp(chunk["created"], tz=timezone.utc)
                                        created_at_str = dt_obj.isoformat(timespec='microseconds') + 'Z'
                                    except Exception:
                                        pass
                                last_created_at = created_at_str

                                # usage 정보 갱신
                                if "usage" in chunk:
                                    usage = chunk["usage"]
                                    final_prompt_eval_count = usage.get("prompt_tokens", final_prompt_eval_count)
                                    final_eval_count = usage.get("completion_tokens", final_eval_count)

                                if finish_reason:
                                    final_done_reason = finish_reason

                                if not done:
                                    if content:
                                        accumulated_content += content
                                        final_eval_count += len(content)
                                        data = {
                                            "model": requested_model,
                                            "created_at": created_at_str,
                                            "message": {
                                                "role": "assistant",
                                                "content": content,
                                            },
                                            "done": False,
                                        }
                                        yield f"{json.dumps(data, ensure_ascii=False)}\n"
                                        print(f"[{datetime.now(timezone.utc).isoformat(timespec='microseconds')}][Bridge Sent Chunk]: {json.dumps(data, ensure_ascii=False)}")
                                else:
                                    # 최종 응답 청크 전송
                                    end_time = time.time()
                                    total_duration = int((end_time - start_time) * 1_000_000_000)
                                    load_duration_ns = current_model_load_duration
                                    prompt_eval_duration_ns = int((first_chunk_time - start_time) * 1_000_000_000) if first_chunk_time else 0
                                    eval_duration_ns = total_duration - prompt_eval_duration_ns
                                    final_data = {
                                        "model": requested_model,
                                        "created_at": last_created_at,
                                        "message": {
                                            "role": "assistant",
                                            "content": "",
                                        },
                                        "done_reason": final_done_reason or "stop",
                                        "done": True,
                                        "total_duration": total_duration,
                                        "load_duration": load_duration_ns,
                                        "prompt_eval_count": final_prompt_eval_count,
                                        "prompt_eval_duration": prompt_eval_duration_ns,
                                        "eval_count": final_eval_count,
                                        "eval_duration": eval_duration_ns
                                    }
                                    yield f"{json.dumps(final_data, ensure_ascii=False)}\n"
                                    print(f"[{datetime.now(timezone.utc).isoformat(timespec='microseconds')}][Bridge Sent DONE Chunk]: {json.dumps(final_data, ensure_ascii=False)}")
                                    await asyncio.sleep(0.01)
                                    break
                            else:
                                print(f"[stream unhandled vLLM chunk] {chunk}")
                except httpx.RequestError as exc:
                    error_msg = f"VLLM API 요청 실패: {exc}"
                    print(f"--- {error_msg} ---")
                    yield f"{json.dumps({
                        'model': requested_model,
                        'created_at': get_current_ollama_created_at_format(),
                        'message': {'role': 'assistant', 'content': f'⚠️ VLLM 서버에 연결할 수 없습니다: {exc}'},
                        'done': True
                    }, ensure_ascii=False)}\n"
                except httpx.HTTPStatusError as exc:
                    error_msg = f"VLLM API HTTP 오류: {exc.response.status_code} - {exc.response.text}"
                    print(f"--- {error_msg} ---")
                    yield f"{json.dumps(
                        {
                            'model': requested_model,
                            'created_at': get_current_ollama_created_at_format(),
                            'message': {'role': 'assistant', 'content': f'⚠️ VLLM 서버에서 오류 응답: {error_msg}'},
                            'done': True
                        }, ensure_ascii=False)}\n"
                except Exception as exc:
                    error_msg = f"스트리밍 처리 중 예상치 못한 오류: {exc}"
                    print(f"--- {error_msg} ---")
                    yield f"{json.dumps({
                        'model': requested_model,
                        'created_at': get_current_ollama_created_at_format(),
                        'message': {'role': 'assistant', 'content': f'⚠️ 브릿지 서버 스트리밍 오류: {exc}'},
                        'done': True
                    }, ensure_ascii=False)}\n"

        return StreamingResponse(stream_vllm(), media_type="application/x-ndjson")

    else:
        # ===============================================================
        # 스트리밍이 아닌 경우 (단일 응답)
        # ===============================================================
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                # vLLM에 POST 요청
                response = await client.post(VLLM_API_URL, json=openai_payload)
                response.raise_for_status()
                resp_json = response.json()
            except httpx.RequestError as exc:
                print(f"--- VLLM API 요청 실패 (비스트리밍): {exc} ---")
                return Response(
                    content=json.dumps({
                        "model": requested_model,
                        "created_at": get_current_ollama_created_at_format(),
                        "message": {
                            "role": "assistant",
                            "content": f"⚠️ VLLM 서버에 연결할 수 없음: {exc}"
                        },
                        "done": True
                    }, ensure_ascii=False),
                    status_code=500,
                    media_type="application/json"
                )
            except httpx.HTTPStatusError as exc:
                print(f"--- VLLM API HTTP 오류 (비스트리밍): {exc.response.status_code} - {exc.response.text} ---")
                return Response(
                    content=json.dumps({
                        "model": requested_model,
                        "created_at": get_current_ollama_created_at_format(),
                        "message": {
                            "role": "assistant",
                            "content": f'⚠️ VLLM 서버에서 오류 응답: {exc.response.status_code} - {exc.response.text}'
                        },
                        "done": True
                    }, ensure_ascii=False),
                    status_code=exc.response.status_code,
                    media_type="application/json"
                )
            except Exception:
                # 예상치 못한 에러
                return Response(
                    content=json.dumps({
                        "model": requested_model,
                        "created_at": get_current_ollama_created_at_format(),
                        "message": {
                            "role": "assistant",
                            "content": "⚠️ vLLM 서버로부터 올바르지 않은 응답 접수; 서버 상태/입력값 확인 필요"
                        },
                        "done": True
                    }, ensure_ascii=False),
                    media_type="application/json"
                )

        # vLLM 응답에 choice가 없는 경우
        if "choices" not in resp_json or not resp_json["choices"]:
            return Response(
                content=json.dumps({
                    "model": requested_model,
                    "created_at": get_current_ollama_created_at_format(),
                    "message": {
                        "role": "assistant",
                        "content": f"⚠️ vLLM에서 결과가 반환되지 않음.\n응답: {resp_json}"
                    },
                    "done": True
                }, ensure_ascii=False),
                media_type="application/json"
            )

        # 응답에서 실제 content 추출
        content = resp_json["choices"][0]["message"]["content"]
        finish_reason = resp_json["choices"][0].get("finish_reason")

        done_status = bool(finish_reason is not None)
        created_at_str = get_current_ollama_created_at_format()
        if "created" in resp_json:
            try:
                dt_obj = datetime.fromtimestamp(resp_json["created"], tz=timezone.utc)
                created_at_str = dt_obj.isoformat(timespec='microseconds') + 'Z'
            except (ValueError, TypeError):
                pass

        # 전체 응답 시간 계산
        end_time = time.time()
        total_duration_ns = int((end_time - start_time) * 1_000_000_000)

        # usage 기반으로 토큰 수 계산 (없을 경우 fallback)
        usage = resp_json.get("usage", {})
        prompt_eval_count_final = usage.get("prompt_tokens") if usage.get("prompt_tokens") is not None else estimated_prompt_tokens
        eval_count_final = usage.get("completion_tokens") if usage.get("completion_tokens") is not None else len(content)

        # 시간 분할 (모델 로딩시간 제외, 전체를 prompt 처리시간으로 가정)
        prompt_eval_duration_ns = total_duration_ns
        eval_duration_ns = 0

        # Ollama 형식에 맞게 최종 응답 구성
        ollama_response = {
            "model": requested_model,
            "created_at": created_at_str,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "done_reason": finish_reason or "stop",
            "done": done_status,
            "total_duration": total_duration_ns,
            "load_duration": current_model_load_duration,
            "prompt_eval_count": prompt_eval_count_final,
            "prompt_eval_duration": prompt_eval_duration_ns,
            "eval_count": eval_count_final,
            "eval_duration": eval_duration_ns
        }

        return Response(
            content=json.dumps(ollama_response, ensure_ascii=False),
            media_type="application/json"
        )

import asyncio
import aiohttp
import json
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
import uvicorn
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv("/root/ladder/.env")

async def run_xray_statsquery():
    command = [
        "docker", "exec", "xray",
        "/usr/bin/xray", "api", "statsquery",
        "--server=127.0.0.1:10085"
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            stderr_text = stderr.decode()
            return {"error": "Command failed", "return_code": process.returncode, "stderr": stderr_text}

        output = stdout.decode()

        # 尝试解析 JSON，如果输出不是 JSON 格式可以跳过这一步
        try:
            data = json.loads(output)
            return data
        except json.JSONDecodeError:
            return {"error": "Invalid JSON output", "output": output}

    except FileNotFoundError:
        return {"error": "Docker or xray command not found", "detail": "Please check if they are installed."}
    except Exception as e:
        return {"error": "Unexpected error", "detail": str(e)}


async def fetch_hy2_traffic():
    url = "http://127.0.0.1:8899/traffic"
    header = {"Authorization": "some_secret"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=header) as response:
                if response.status == 200:
                    text = await response.text()
                    try:
                        data = json.loads(text)
                        return data
                    except json.JSONDecodeError:
                        return {"error": "Invalid JSON response", "response": text}
                else:
                    error_text = await response.text()
                    return {"error": f"Unexpected status code: {response.status}", "response": error_text}
    except aiohttp.ClientError as e:
        return {"error": "Network error", "detail": str(e)}
    except asyncio.TimeoutError:
        return {"error": "Request timed out"}
    except Exception as e:
        return {"error": "Unexpected error", "detail": str(e)}

# 创建 FastAPI 应用
app = FastAPI(title="Traffic Monitor API", description="API for monitoring xray and hy2 traffic")

class PasswordModel(BaseModel):
    password: str

async def validate_password(request: Request):
    try:
        data = await request.json()
        password_model = PasswordModel(**data)
        if password_model.password != os.getenv("STAT_PASSWORD"):
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid password")
        return data
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

@app.post("/traffic/xray")
async def get_xray_traffic(data: dict = Depends(validate_password)):
    data = await run_xray_statsquery()
    
    # 检查是否包含错误信息
    if data and "error" in data:
        return JSONResponse(
            status_code=500,
            content=data
        )
    
    if data:
        return data
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve xray traffic data"}
        )

@app.post("/traffic/hy2")
async def get_hy2_traffic(data: dict = Depends(validate_password)):
    data = await fetch_hy2_traffic()
    
    # 检查是否包含错误信息
    if data and "error" in data:
        return JSONResponse(
            status_code=500,
            content=data
        )
    
    if data:
        return data
    else:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to retrieve hy2 traffic data"}
        )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7889)


import json
import os
import glob
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
import send2trash

# Local modules
import database
import image_processing

import logging

# --- Use Uvicorn's Standard Logger ---
logger = logging.getLogger("uvicorn")

CONFIG_FILE = "config.json"

app = FastAPI()

# --- Global Scan Status ---
SCAN_STATUS = {
    "is_running": False,
    "current": 0,
    "total": 0,
    "message": ""
}

# --- Mount static files for the frontend ---
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# --- Pydantic Models ---
class AppConfig(BaseModel):
    image_file_path: str
    des_file_path: str

class DeleteRequest(BaseModel):
    image_ids: list[int]

# --- Configuration ---
def get_config(mount_images=True):
    """
    Reads the config file. If mount_images is True, it will also mount 
    the destination directory to serve classified images.
    """
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        logger.info(f"Loaded config: {config_data}")
        if mount_images and config_data.get("des_file_path") and os.path.isdir(config_data["des_file_path"]):
            app.mount("/images", StaticFiles(directory=config_data["des_file_path"]), name="images")
        return config_data

def save_config(config: AppConfig):
    """Saves the configuration and re-mounts the /images static directory."""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config.dict(), f, indent=4)
    # Re-mount the images directory with the new path
    get_config(mount_images=True)

# --- Background Task for Scanning ---
def scan_and_process_images(source_path: str, dest_path: str):
    """Scans the source path for images and processes them in the background."""
    global SCAN_STATUS
    database.create_table_if_not_exists() 
    
    SCAN_STATUS["is_running"] = True
    SCAN_STATUS["message"] = "파일 검색 중..."
    
    logger.info(f"Starting scan in background: {source_path}")
    extensions = ['*.png', '*.jpg', '*.jpeg', '*.webp', '*.mp4', '*.webm', '*.gif']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(source_path, '**', ext), recursive=True))
    
    SCAN_STATUS["total"] = len(files)
    SCAN_STATUS["current"] = 0
    SCAN_STATUS["message"] = "이미지 처리 중..."
    
    processed_count = 0
    for file in files:
        try:
            image_data = image_processing.process_image(file, dest_path)
            if image_data:
                database.add_image_info(image_data)
                processed_count += 1
            SCAN_STATUS["current"] += 1
        except Exception as e:
            logger.error(f"Failed to process {file}: {e}")
            SCAN_STATUS["current"] += 1
            
    logger.info(f"Background scan finished. Processed {processed_count} files.")
    SCAN_STATUS["message"] = "폴더 정리 중..."
    
    # 비어있는 폴더 정리
    try:
        image_processing.remove_empty_folders(source_path)
    except Exception as e:
        logger.error(f"Failed to cleanup empty folders: {e}")
        
    SCAN_STATUS["is_running"] = False
    SCAN_STATUS["message"] = f"완료 ({processed_count}개 처리됨)"

# --- API Endpoints ---
@app.on_event("startup")
def startup_event():
    """On startup, initialize DB and load config."""
    print("\n" + "="*50, flush=True)
    print("  TAG GALLERY SERVER STARTED", flush=True)
    print("  LOGGING IS ACTIVE", flush=True)
    print("="*50 + "\n", flush=True)
    print("Startup event triggered.", flush=True)
    database.create_table_if_not_exists()
    get_config(mount_images=True)

@app.get("/")
async def read_root(request: Request):
    """Serves the main index.html file."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/config")
def read_config():
    """Returns the current configuration."""
    config = get_config(mount_images=False)
    if not config:
        logger.warning("Configuration file not found.")
        raise HTTPException(status_code=404, detail="Configuration not found. Please set it up.")
    logger.info(f"API returning config: {config}")
    return config

@app.post("/api/config")
def write_config(config: AppConfig):
    """Saves a new configuration."""
    try:
        if not os.path.isdir(config.image_file_path):
            raise HTTPException(status_code=400, detail=f"Source path not found: {config.image_file_path}")
        os.makedirs(config.des_file_path, exist_ok=True)
        save_config(config)
        return {"message": "Configuration saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan")
def start_scan(background_tasks: BackgroundTasks):
    """Starts the image scan and classification in the background."""
    if SCAN_STATUS["is_running"]:
        return {"message": "Image scan is already running.", "status": SCAN_STATUS}
        
    config = get_config(mount_images=False)
    if not config or not config.get("image_file_path") or not config.get("des_file_path"):
        raise HTTPException(status_code=400, detail="Configuration is not set properly.")
    
    source_path = config["image_file_path"]
    dest_path = config["des_file_path"]
    
    logger.info(f"Scan request received from frontend. Source: {source_path}")
    background_tasks.add_task(scan_and_process_images, source_path, dest_path)
    return {"message": "Image scan started in the background."}

@app.get("/api/scan/status")
def get_scan_status():
    """Returns the current status of the background scan."""
    return SCAN_STATUS

def _format_image_path(image, config):
    """Helper to convert absolute path to /images/ relative URL."""
    if not config:
        return image
    base_path = config["des_file_path"]
    if os.path.exists(image["filepath"]):
        relative_path = os.path.relpath(image["filepath"], base_path)
        image["filepath"] = "/images/" + relative_path.replace("\\", "/")
    else:
        image["filepath"] = "/static/placeholder.png"
    return image

@app.get("/api/images")
def get_all_images(page: int = 1, limit: int = 50, query: Optional[str] = None, sort_by: str = "random", platform_filter: str = "all", seed: Optional[str] = None, video_only: bool = False, favorites_only: bool = False):
    """Retrieves a paginated list of images, with optional search, sorting and platform filtering."""
    try:
        parsed_seed = None
        if seed and seed.isdigit():
            parsed_seed = int(seed)
        
        result = database.get_images(page, limit, query, sort_by, platform_filter, parsed_seed, video_only, favorites_only)
        config = get_config(mount_images=False)
        for img in result["images"]:
            _format_image_path(img, config)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve images: {e}")

@app.get("/api/images/{image_id}")
def get_single_image(image_id: int):
    """Retrieves detailed information for a single image."""
    try:
        image = database.get_image_by_id(image_id)
        if image is None:
            raise HTTPException(status_code=404, detail="Image not found")
        
        config = get_config(mount_images=False)
        _format_image_path(image, config)
        return image
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve image details: {e}")

@app.post("/api/images/{image_id}/favorite")
def toggle_favorite(image_id: int, favorite: bool):
    """Toggles the favorite status of an image."""
    try:
        database.update_image_favorite(image_id, favorite)
        return {"message": "Favorite status updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update favorite status: {e}")

@app.get("/api/images/{image_id}/similar")
def get_similar_images_api(image_id: int, limit: int = 20):
    """Fetches images similar to the given image ID."""
    try:
        results = database.get_similar_images(image_id, limit)
        config = get_config(mount_images=False)
        for img in results:
            _format_image_path(img, config)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch similar images: {e}")

@app.delete("/api/images/batch")
def delete_images_batch(request: DeleteRequest):
    try:
        logger.info(f"삭제 요청 수신: {len(request.image_ids)}개의 ID")
        filepaths = database.delete_images_by_ids(request.image_ids)
        logger.info(f"DB에서 조회된 파일 경로 수: {len(filepaths)}개")
        deleted_count = 0
        for filepath in filepaths:
            if os.path.exists(filepath):
                send2trash.send2trash(filepath)
                deleted_count += 1
                logger.info(f"파일을 휴지통으로 이동했습니다: {filepath}")
                
                # 비디오 썸네일도 삭제
                thumb_path = filepath + ".thumb.jpg"
                if os.path.exists(thumb_path):
                    send2trash.send2trash(thumb_path)
                    logger.info(f"동영상 썸네일을 휴지통으로 이동했습니다: {thumb_path}")
            else:
                logger.warning(f"경고: 파일을 찾을 수 없어 휴지통으로 이동하지 못했습니다: {filepath}")
        return {"message": f"{len(request.image_ids)}개의 레코드를 데이터베이스에서 삭제하고, {deleted_count}개의 파일을 휴지통으로 이동했습니다."}
    except Exception as e:
        logger.error(f"이미지 삭제 실패: {e}")
        raise HTTPException(status_code=500, detail=f"이미지 삭제 실패: {e}")
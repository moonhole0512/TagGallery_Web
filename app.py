import json
import os
import glob
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

CONFIG_FILE = "config.json"

app = FastAPI()

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
        if mount_images and os.path.isdir(config_data.get("des_file_path", "")):
            # To avoid errors on reload, we can try to unmount first, but a simple
            # check and mount is often sufficient if the path doesn't change.
            # A more robust solution would manage mounts more carefully if paths change frequently.
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
    database.create_table_if_not_exists() # Ensure table exists for the background process
    print(f"Starting scan in background: {source_path}")
    png_files = glob.glob(os.path.join(source_path, '**', '*.png'), recursive=True)
    processed_count = 0
    for png_file in png_files:
        try:
            image_data = image_processing.process_image(png_file, dest_path)
            if image_data:
                database.add_image_info(image_data)
                processed_count += 1
                print(f"Processed: {png_file}")
        except Exception as e:
            print(f"Failed to process {png_file}: {e}")
    print(f"Background scan finished. Processed {processed_count} images.")

# --- API Endpoints ---
@app.on_event("startup")
def startup_event():
    """On startup, initialize DB and load config."""
    # database.init_db() # This will wipe the DB on every restart. Better to do it manually.
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
        raise HTTPException(status_code=404, detail="Configuration not found. Please set it up.")
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
    config = get_config(mount_images=False)
    if not config or not config.get("image_file_path") or not config.get("des_file_path"):
        raise HTTPException(status_code=400, detail="Configuration is not set properly.")
    
    source_path = config["image_file_path"]
    dest_path = config["des_file_path"]
    
    background_tasks.add_task(scan_and_process_images, source_path, dest_path)
    return {"message": "Image scan started in the background."}

@app.get("/api/images")
def get_all_images(page: int = 1, limit: int = 50, query: Optional[str] = None, sort_by: str = "random", platform_filter: str = "all"):
    """Retrieves a paginated list of images, with optional search, sorting and platform filtering."""
    try:
        result = database.get_images(page, limit, query, sort_by, platform_filter)
        config = get_config(mount_images=False)
        if config:
            base_path = config["des_file_path"]
            for img in result["images"]:
                if os.path.exists(img["filepath"]):
                    relative_path = os.path.relpath(img["filepath"], base_path)
                    img["filepath"] = "/images/" + relative_path.replace("\\", "/")
                else:
                    img["filepath"] = "/static/placeholder.png" # Placeholder for missing files
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
        if config:
            base_path = config["des_file_path"]
            if os.path.exists(image["filepath"]):
                relative_path = os.path.relpath(image["filepath"], base_path)
                image["filepath"] = "/images/" + relative_path.replace("\\", "/")
            else:
                image["filepath"] = "/static/placeholder.png"
        
        return image
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve image details: {e}")

@app.delete("/api/images/batch")
async def delete_images_batch(request: DeleteRequest):
    try:
        filepaths = database.delete_images_by_ids(request.image_ids)
        deleted_count = 0
        for filepath in filepaths:
            if os.path.exists(filepath):
                send2trash.send2trash(filepath)
                deleted_count += 1
                print(f"파일을 휴지통으로 이동했습니다: {filepath}")
            else:
                print(f"경고: 파일을 찾을 수 없어 휴지통으로 이동하지 못했습니다: {filepath}")
        return {"message": f"{len(request.image_ids)}개의 레코드를 데이터베이스에서 삭제하고, {deleted_count}개의 파일을 휴지통으로 이동했습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"이미지 삭제 실패: {e}")
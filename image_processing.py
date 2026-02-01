import os
import json
import gzip
from PIL import Image
from datetime import datetime
import traceback
import cv2
from mutagen.mp4 import MP4
import mutagen
import logging
import send2trash

logger = logging.getLogger("uvicorn")

def read_info_from_image_stealth(image):
    # if tensor, convert to PIL image
    if hasattr(image, 'cpu'):
        image = image.cpu().numpy() #((1, 1, 1280, 3), '<f4')
        image = image[0].astype('uint8') #((1, 1280, 3), 'uint8')
        image = Image.fromarray(image)
    # trying to read stealth pnginfo
    width, height = image.size
    pixels = image.load()

    has_alpha = True if image.mode == 'RGBA' else False
    mode = None
    compressed = False
    binary_data = ''
    buffer_a = ''
    buffer_rgb = ''
    index_a = 0
    index_rgb = 0
    sig_confirmed = False
    confirming_signature = True
    reading_param_len = False
    reading_param = False
    read_end = False
    never_confirmed = True
    for x in range(width):
        for y in range(height):
            if has_alpha:
                r, g, b, a = pixels[x, y]
                buffer_a += str(a & 1)
                index_a += 1
            else:
                r, g, b = pixels[x, y]
            buffer_rgb += str(r & 1)
            buffer_rgb += str(g & 1)
            buffer_rgb += str(b & 1)
            index_rgb += 3
            if confirming_signature:
                if x * height + y > 120 and never_confirmed:
                    return ''
                if index_a == len('stealth_pnginfo') * 8:
                    decoded_sig = bytearray(int(buffer_a[i:i + 8], 2) for i in
                                            range(0, len(buffer_a), 8)).decode('utf-8', errors='ignore')
                    if decoded_sig in {'stealth_pnginfo', 'stealth_pngcomp'}:
                        #print(f"Found signature at {x}, {y}")
                        confirming_signature = False
                        sig_confirmed = True
                        reading_param_len = True
                        mode = 'alpha'
                        if decoded_sig == 'stealth_pngcomp':
                            compressed = True
                        buffer_a = ''
                        index_a = 0
                        never_confirmed = False
                    else:
                        read_end = True
                        break
                elif index_rgb == len('stealth_pnginfo') * 8:
                    decoded_sig = bytearray(int(buffer_rgb[i:i + 8], 2) for i in
                                            range(0, len(buffer_rgb), 8)).decode('utf-8', errors='ignore')
                    if decoded_sig in {'stealth_rgbinfo', 'stealth_rgbcomp'}:
                        #print(f"Found signature at {x}, {y}")
                        confirming_signature = False
                        sig_confirmed = True
                        reading_param_len = True
                        mode = 'rgb'
                        if decoded_sig == 'stealth_rgbcomp':
                            compressed = True
                        buffer_rgb = ''
                        index_rgb = 0
                        never_confirmed = False
            elif reading_param_len:
                if mode == 'alpha':
                    if index_a == 32:
                        param_len = int(buffer_a, 2)
                        reading_param_len = False
                        reading_param = True
                        buffer_a = ''
                        index_a = 0
                else:
                    if index_rgb == 33:
                        pop = buffer_rgb[-1]
                        buffer_rgb = buffer_rgb[:-1]
                        param_len = int(buffer_rgb, 2)
                        reading_param_len = False
                        reading_param = True
                        buffer_rgb = pop
                        index_rgb = 1
            elif reading_param:
                if mode == 'alpha':
                    if index_a == param_len:
                        binary_data = buffer_a
                        read_end = True
                        break
                else:
                    if index_rgb >= param_len:
                        diff = param_len - index_rgb
                        if diff < 0:
                            buffer_rgb = buffer_rgb[:diff]
                        binary_data = buffer_rgb
                        read_end = True
                        break
            else:
                # impossible
                read_end = True
                break
        if read_end:
            break
    geninfo = ''
    if sig_confirmed and binary_data != '':
        # Convert binary string to UTF-8 encoded text
        byte_data = bytearray(int(binary_data[i:i + 8], 2) for i in range(0, len(binary_data), 8))
        try:
            if compressed:
                decoded_data = gzip.decompress(bytes(byte_data)).decode('utf-8')
            else:
                decoded_data = byte_data.decode('utf-8', errors='ignore')
            geninfo = decoded_data
        except:
            pass
    return str(geninfo)

def check_img_width(img):
    width, _ = img.size
    return width

def check_platform_name(img):
    metadata = img.info
    try:
        if 'Comment' in metadata:
            return "NovelAI"
        elif 'parameters' in metadata:
            return "StableDiffusion"
        elif 'prompt' in metadata or 'workflow' in metadata:
            return "ComfyUI"
        else:
            stealth_info = read_info_from_image_stealth(img)
            if stealth_info:
                try:
                    decoded = json.loads(stealth_info)
                    return decoded.get('Software', "Unknown")
                except:
                    return "Unknown"
            return "Unknown"
    except Exception:
        return "Unknown"

def extract_video_metadata(file_path):
    """
    동영상의 메타데이터(설명/주석)에서 ComfyUI 정보를 추출합니다.
    """

    print(f"테스트Extracting metadata from {file_path}", flush=True)

    try:
        metadata_dict = {}
        platform = "Unknown"
        
        try:
            # mutagen.File로 먼저 시도
            video = mutagen.File(file_path)
            # MP4의 경우 가끔 mutagen.File이 실패하거나 MP4 객체로 다루는게 더 정확함
            if file_path.lower().endswith('.mp4'):
                try:
                    video_mp4 = MP4(file_path)
                    if video_mp4:
                        video = video_mp4
                except:
                    pass
            
            if video is None:
                print(f"테스트: mutagen failure - could not read metadata from {file_path}", flush=True)
                return platform, metadata_dict

            best_metadata = {}
            best_platform = "Unknown"
            fallback_comment = ""

            print(f"테스트1", flush=True)
            print(f"테스트: metadata keys found: {list(video.keys())}", flush=True)

            # 가능한 모든 메타데이터 키 후보들을 순회하며 확인 (대소문자 무시)
            for key in video.keys():
                k_lower = key.lower()
                # 설명, 주석 관련 키워드 확인
                if any(x in k_lower for x in ["des", "cmt", "comment", "description"]):
                    val = video.get(key)
                    if not val:
                        continue
                        
                    if isinstance(val, (list, tuple)) and len(val) > 0:
                        description = str(val[0])
                    else:
                        description = str(val)
                    
                    description = description.strip()
                    if not description:
                        continue
                    
                    # 1. JSON 형식인지 확인 및 파싱 시도
                    if description.startswith('{') and description.endswith('}'):
                        try:
                            data = json.loads(description)
                            
                            # ComfyUI 여부 판별 로직
                            is_comfy = False
                            prompt_data = None
                            
                            print(f"테스트2", flush=True)

                            # prompt 키 내부 구조 확인
                            if "prompt" in data:
                                try:
                                    if isinstance(data["prompt"], str):
                                        prompt_data = json.loads(data["prompt"])
                                    else:
                                        prompt_data = data["prompt"]
                                except:
                                    pass
                            
                            print(f"테스트3", flush=True)

                            if prompt_data and isinstance(prompt_data, dict):
                                for node_id in prompt_data:
                                    if isinstance(prompt_data[node_id], dict) and "class_type" in prompt_data[node_id]:
                                        is_comfy = True
                                        break
                            
                            print(f"테스트4", flush=True)

                            if not is_comfy:
                                if "workflow" in data:
                                    is_comfy = True
                                elif "extra" in data and isinstance(data["extra"], dict):
                                    is_comfy = True
                            
                            if is_comfy:
                                # ComfyUI를 찾았으면 더 볼 필요 없이 즉시 반환
                                platform = "ComfyUI"
                                metadata_dict = data
                                if prompt_data:
                                    metadata_dict["prompt"] = prompt_data
                                if "Software" not in metadata_dict:
                                    metadata_dict["Software"] = "ComfyUI"
                                return platform, metadata_dict
                            else:
                                # ComfyUI는 아니지만 JSON인 경우 후보로 저장
                                best_metadata = data
                            
                            print(f"테스트5", flush=True)

                        except json.JSONDecodeError:
                            # JSON 파싱 실패시 일반 텍스트 후보로 저장
                            fallback_comment = description
                    else:
                        # JSON이 아닌 일반 텍스트
                        fallback_comment = description

            # 루프가 끝날 때까지 ComfyUI를 못 찾았으면 수집된 최선의 결과물 반환
            if best_metadata:
                metadata_dict = best_metadata
            elif fallback_comment:
                metadata_dict = {"comment": fallback_comment}
                
        except Exception as e:
            print(f"Error reading mutagen metadata for {file_path}: {e}", flush=True)

        return platform, metadata_dict
    except Exception as e:
        print(f"Error in extract_video_metadata for {file_path}: {e}", flush=True)
        return "Unknown", {}

def extract_video_frame(video_path, thumb_path):
    """
    동영상의 첫 번째 프레임을 추출하여 썸네일로 저장합니다.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        success, image = cap.read()
        if success:
            # 퀄리티 조절을 위해 encode 파라미터 사용 가능
            cv2.imwrite(thumb_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        cap.release()
        return success
    except Exception as e:
        print(f"Error extracting video frame for {video_path}: {e}", flush=True)
        return False

def process_image(file_path, dest_root_path):
    """
    이미지 또는 동영상 파일을 처리하고, 메타데이터를 추출하며, 파일을 분류/이동합니다.

    :param file_path: 처리할 원본 파일 경로
    :param dest_root_path: 분류된 파일이 저장될 최상위 경로
    :return: 성공 시 {'new_path': str, 'make_time': str, 'platform': str, 'metadata': dict}, 실패 시 None
    """
    try:
        new_path = None
        metadata_dict = {}
        platform = "Unknown"
        make_time_str = ""
        
        lower_path = file_path.lower()
        is_video = lower_path.endswith(('.mp4', '.webm', '.gif'))
        is_image = lower_path.endswith(('.png', '.jpg', '.jpeg', '.webp'))

        make_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        make_time_str = make_time.strftime('%y%m%d_%H%M%S')
        create_date_str = make_time.strftime('%y%m%d')

        if is_image:
            with Image.open(file_path) as img:
                platform = check_platform_name(img)
                
                # 이미지 너비가 2000 이하일 때만 메타데이터 추출 시도
                if check_img_width(img) <= 2000:
                    try:
                        raw_metadata = img.info
                        if 'Comment' in raw_metadata: # NovelAI
                            metadata_dict = json.loads(raw_metadata['Comment'])
                            metadata_dict['Software'] = raw_metadata.get('Software', 'NovelAI')
                            metadata_dict['Source'] = raw_metadata.get('Source')
                            metadata_dict['Title'] = raw_metadata.get('Title')
                        elif 'parameters' in raw_metadata: # Stable Diffusion
                            metadata_dict['prompt'] = raw_metadata['parameters']
                            metadata_dict['Software'] = 'StableDiffusion'
                        elif 'prompt' in raw_metadata: # ComfyUI
                            metadata_dict['prompt'] = json.loads(raw_metadata['prompt'])
                            if 'workflow' in raw_metadata:
                                metadata_dict['workflow'] = json.loads(raw_metadata['workflow'])
                            metadata_dict['Software'] = 'ComfyUI'
                        else: # Stealth PNG Info
                            stealth_info = read_info_from_image_stealth(img)
                            if stealth_info:
                                full_info = json.loads(stealth_info)
                                comment_info = json.loads(full_info.get('Comment', '{}'))
                                metadata_dict.update(comment_info)
                                metadata_dict['Software'] = full_info.get('Software')
                                metadata_dict['Source'] = full_info.get('Source')
                    except Exception as e:
                        logger.error(f"Error extracting metadata for {file_path}: {e}")
        elif is_video:
            # 동영상의 메타데이터 추출 시도
            platform, metadata_dict = extract_video_metadata(file_path)
        else:
            return None

        dest_folder = os.path.join(dest_root_path, platform, create_date_str)
        os.makedirs(dest_folder, exist_ok=True)
        
        new_path = os.path.join(dest_folder, os.path.basename(file_path))

        if os.path.exists(new_path):
            print(f"File {os.path.basename(file_path)} already exists. Skipping.", flush=True)
            return None

        # 비디오의 경우 썸네일 생성 (이동 전 원본 경로 기반 혹은 이동 후?)
        # 안정성을 위해 원본을 이동한 후 생성
        os.rename(file_path, new_path)
        
        if is_video:
            thumb_path = new_path + ".thumb.jpg"
            extract_video_frame(new_path, thumb_path)

        return {
            "new_path": os.path.abspath(new_path),
            "make_time": make_time_str,
            "platform": platform,
            "metadata": metadata_dict
        }

    except Exception as e:
        print(f"Error processing file {file_path}: {e}", flush=True)
        traceback.print_exc()
        return None

def remove_empty_folders(folder_path):
    """
    지정된 폴더 내의 비어있는 하위 폴더들을 재귀적으로 탐색하여 휴지통으로 삭제합니다.
    bottom-up 방식을 사용하여 하위 폴더가 삭제된 후 비게 되는 상위 폴더도 삭제할 수 있습니다.
    """
    logger.info(f"Checking for empty folders in: {folder_path}")
    if not os.path.exists(folder_path):
        return

    for root, dirs, files in os.walk(folder_path, topdown=False):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                # 폴더가 비어있는지 확인 (os.listdir가 비어있으면)
                if not os.listdir(dir_path):
                    logger.info(f"Removing empty folder to trash: {dir_path}")
                    send2trash.send2trash(dir_path)
            except Exception as e:
                logger.error(f"Error removing folder {dir_path}: {e}")

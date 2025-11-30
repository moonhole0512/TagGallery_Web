import os
import json
import gzip
from PIL import Image
from datetime import datetime
import traceback

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
        else:
            stealth_info = read_info_from_image_stealth(img)
            if stealth_info:
                return json.loads(stealth_info).get('Software', "Unknown")
            return "Unknown"
    except Exception:
        return "Unknown"

def process_image(image_path, dest_root_path):
    """
    이미지 파일을 처리하고, 메타데이터를 추출하며, 파일을 분류/이동합니다.

    :param image_path: 처리할 원본 이미지 파일 경로
    :param dest_root_path: 분류된 이미지가 저장될 최상위 경로
    :return: 성공 시 {'new_path': str, 'make_time': str, 'platform': str, 'metadata': dict}, 실패 시 None
    """
    try:
        new_path = None
        metadata_dict = {}
        platform = "Unknown"
        make_time_str = ""

        with Image.open(image_path) as img:
            platform = check_platform_name(img)
            make_time = datetime.fromtimestamp(os.path.getmtime(image_path))
            make_time_str = make_time.strftime('%y%m%d_%H%M%S')
            create_date_str = make_time.strftime('%y%m%d')

            dest_folder = os.path.join(dest_root_path, platform, create_date_str)
            os.makedirs(dest_folder, exist_ok=True)
            
            new_path = os.path.join(dest_folder, os.path.basename(image_path))

            if os.path.exists(new_path):
                print(f"File {os.path.basename(image_path)} already exists. Skipping.")
                return None

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
                    else: # Stealth PNG Info
                        stealth_info = read_info_from_image_stealth(img)
                        if stealth_info:
                            full_info = json.loads(stealth_info)
                            comment_info = json.loads(full_info.get('Comment', '{}'))
                            metadata_dict.update(comment_info)
                            metadata_dict['Software'] = full_info.get('Software')
                            metadata_dict['Source'] = full_info.get('Source')

                except Exception as e:
                    print(f"Error extracting metadata for {image_path}: {e}")
                    traceback.print_exc()
        
        # 'with' 블록이 끝난 후, 파일 핸들이 닫힌 상태에서 파일 이동
        if new_path:
            os.rename(image_path, new_path)
            return {
                "new_path": os.path.abspath(new_path),
                "make_time": make_time_str,
                "platform": platform,
                "metadata": metadata_dict
            }
        
        return None

    except Exception as e:
        print(f"Error processing image {image_path}: {e}")
        traceback.print_exc()
        return None

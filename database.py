import sqlite3
import json
import math
from typing import Optional


DB_FILE = "image_gallery.db"

def sanitize_metadata(obj):
    """
    Recursively replaces non-JSON compliant float values (NaN, Inf) with None.
    """
    if isinstance(obj, dict):
        return {k: sanitize_metadata(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_metadata(i) for i in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj

def create_table_if_not_exists():
    """테이블이 존재하지 않으면 생성합니다. 기존 테이블에 컬럼이 없으면 추가합니다."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS NAIimgInfo
                          (no INTEGER PRIMARY KEY AUTOINCREMENT,
                           filepath TEXT NOT NULL UNIQUE,
                           makeTime TEXT,
                           platform TEXT,
                           metadata TEXT)''')
        
        # is_favorite 컬럼 추가 (마이그레이션)
        cursor.execute("PRAGMA table_info(NAIimgInfo)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'is_favorite' not in columns:
            cursor.execute("ALTER TABLE NAIimgInfo ADD COLUMN is_favorite INTEGER DEFAULT 0")
            print("Added is_favorite column to NAIimgInfo table.")
            
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error while ensuring table exists: {e}", flush=True)
    finally:
        if conn:
            conn.close()

def init_db():
    """
    데이터베이스를 초기화하고 새로운 스키마로 테이블을 생성합니다.
    기존 테이블이 있다면 삭제하고 새로 만듭니다.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS NAIimgInfo")
        cursor.execute('''CREATE TABLE NAIimgInfo
                          (no INTEGER PRIMARY KEY AUTOINCREMENT,
                           filepath TEXT NOT NULL UNIQUE,
                           makeTime TEXT,
                           platform TEXT,
                           metadata TEXT,
                           is_favorite INTEGER DEFAULT 0)''')
        conn.commit()
        print("Database initialized successfully with the new schema (including favorites).")
    except sqlite3.Error as e:
        print(f"Database error: {e}", flush=True)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환합니다."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    
    # 시드 기반 랜덤 정렬을 위한 사용자 정의 함수 등록
    def seeded_random(id_val, seed):
        import hashlib
        # ID와 시드를 조합하여 해시 생성 후 정수로 변환하여 반환
        hash_input = f"{id_val}:{seed}".encode()
        return hashlib.md5(hash_input).hexdigest()
    
    conn.create_function("seeded_random", 2, seeded_random)
    return conn

def add_image_info(image_data):
    """이미지 정보를 데이터베이스에 추가하거나 업데이트합니다 (UPSERT)."""
    sql = '''INSERT OR REPLACE INTO NAIimgInfo (filepath, makeTime, platform, metadata)
             VALUES (?, ?, ?, ?)'''
    conn = get_db_connection()
    try:
        conn.execute(sql, (
            image_data['new_path'],
            image_data['make_time'],
            image_data['platform'],
            json.dumps(image_data['metadata'])
        ))
        conn.commit()
    finally:
        conn.close()

def get_images(page = 1, limit = 50, query = None, sort_by: str = "random", platform_filter: str = "all", seed: Optional[int] = None, video_only: bool = False, favorites_only: bool = False):
    """
    이미지 목록을 페이지네이션하여 반환합니다. 태그 검색, 정렬 및 플랫폼 필터링을 지원합니다.
    """
    offset = (page - 1) * limit
    conn = get_db_connection()
    
    sql_parts = ["SELECT no, filepath, platform, makeTime, is_favorite FROM NAIimgInfo"]
    count_sql_parts = ["SELECT COUNT(*) FROM NAIimgInfo"]
    
    where_clauses = []
    params = []
    count_params = []
    
    if query:
        where_clauses.append("(json_extract(metadata, '$.prompt') LIKE ? OR json_extract(metadata, '$.uc') LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
        count_params.extend([f"%{query}%", f"%{query}%"])

    if platform_filter != "all":
        if platform_filter == "none":
            where_clauses.append("platform IS NULL OR platform = '' OR platform = 'Unknown'")
        else:
            where_clauses.append("platform = ?")
            params.append(platform_filter)
            count_params.append(platform_filter)

    if video_only:
        where_clauses.append("(filepath LIKE '%.mp4' OR filepath LIKE '%.webm' OR filepath LIKE '%.gif')")

    if favorites_only:
        where_clauses.append("is_favorite = 1")

    if where_clauses:
        sql_parts.append(" WHERE " + " AND ".join(where_clauses))
        count_sql_parts.append(" WHERE " + " AND ".join(where_clauses))

    # 정렬 옵션 처리
    if sort_by == "desc":
        sql_parts.append(" ORDER BY makeTime DESC")
    elif sort_by == "asc":
        sql_parts.append(" ORDER BY makeTime ASC")
    else: # "random" 또는 기본값
        if seed is not None:
            sql_parts.append(" ORDER BY seeded_random(no, ?)")
            params.append(seed)
        else:
            sql_parts.append(" ORDER BY RANDOM()")

    sql_parts.append(" LIMIT ? OFFSET ?")
    params.extend([limit, offset])
    
    sql = " ".join(sql_parts)
    count_sql = " ".join(count_sql_parts)

    cursor = conn.cursor()
    images = cursor.execute(sql, params).fetchall()
    
    total_images = conn.cursor().execute(count_sql, count_params).fetchone()[0]
        
    conn.close()
    
    total_pages = (total_images + limit - 1) // limit
    return {
        "images": [dict(ix) for ix in images],
        "page": page,
        "limit": limit,
        "total_images": total_images,
        "total_pages": total_pages
    }

def get_image_by_id(image_id):
    """ID로 특정 이미지의 모든 정보를 조회합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    image = cursor.execute("SELECT * FROM NAIimgInfo WHERE no = ?", (image_id,)).fetchone()
    conn.close()
    if image is None:
        return None
    
    image_dict = dict(image)
    image_dict['metadata'] = sanitize_metadata(json.loads(image_dict['metadata']))
    return image_dict

def delete_images_by_ids(image_ids: list[int]) -> list[str]:
    """
    주어진 이미지 ID 목록에 해당하는 이미지들을 데이터베이스에서 삭제하고,
    삭제된 이미지들의 파일 경로 목록을 반환합니다.
    """
    conn = get_db_connection()
    filepaths_to_delete = []
    try:
        cursor = conn.cursor()
        
        # 삭제할 파일 경로들을 미리 조회합니다.
        placeholders = ','.join(['?' for _ in image_ids])
        select_sql = f"SELECT filepath FROM NAIimgInfo WHERE no IN ({placeholders})"
        file_records = cursor.execute(select_sql, image_ids).fetchall()
        
        for record in file_records:
            filepaths_to_delete.append(record['filepath'])
            
        # 이미지 레코드들을 삭제합니다.
        delete_sql = f"DELETE FROM NAIimgInfo WHERE no IN ({placeholders})"
        cursor.execute(delete_sql, image_ids)
        
        conn.commit()
        print(f"데이터베이스에서 {len(filepaths_to_delete)}개의 이미지 레코드를 삭제했습니다.", flush=True)
        return filepaths_to_delete
    except sqlite3.Error as e:
        conn.rollback()
        print(f"데이터베이스 오류로 이미지 삭제에 실패했습니다: {e}", flush=True)
        raise
    finally:
        conn.close()

def update_image_favorite(image_id: int, is_favorite: bool):
    """이미지의 즐겨찾기 상태를 업데이트합니다."""
    conn = get_db_connection()
    try:
        conn.execute("UPDATE NAIimgInfo SET is_favorite = ? WHERE no = ?", (1 if is_favorite else 0, image_id))
        conn.commit()
    finally:
        conn.close()

def get_similar_images(image_id: int, limit: int = 20):
    """
    주어진 이미지와 유사한 이미지를 찾습니다.
    개선된 로직: 랭킹 시스템 (Artist/Character/LoRA 가점), 100+ 정크 태그 필터링, 가중치 태그 파싱.
    """
    image = get_image_by_id(image_id)
    if not image or not image.get('metadata'):
        return []
    
    metadata = image.get('metadata', {})
    prompt = metadata.get('prompt', '')
    
    if not prompt or not isinstance(prompt, str):
        return []

    results = []
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # 1. 정크 태그 리스트 확장 (데이터셋의 일반적 단어들)
        JUNK_TAGS = {
            # 인원 및 기본
            '1boy', '2boys', '3boys', 'multiple boys', '1girl', '2girls', '3girls', 'multiple girls', 'solo',
            'masterpiece', 'best quality', 'amazing quality', 'very aesthetic', 'absurdres', 'newest', 'latest',
            'highres', 'quality', 'detailed', 'detailed skin', 'realistic', 'realistic skin', 'realistic light',
            'scenery', 'volumetric lighting', 'light', 'background', 'simple background', 'white background',
            # 포즈 및 시선
            'looking at viewer', 'focus on female', 'focus on male', 'looking ahead', 'looking back',
            'standing', 'sitting', 'lying', 'from side', 'from behind', 'from above', 'from below',
            'manga cover', 'official art', 'censor', 'uncensored', 'bar_censor', 'jpeg artifacts',
            'sketch', 'signature', 'watermark', 'old', 'oldest', 'blush', 'smile', 'blushing', 'artist name',
            # 해부학/포르노그래피 (너무 흔해서 변별력 없는 경우)
            'penis', 'pussy', 'vaginal', 'anus', 'ass', 'breasts', 'large breasts', 'nipples', 'cum', 
            'sex', 'insertion', 'penetration', 'missionary', 'cowgirl', 'nude', 'naked', 'hetero',
            'after sex', 'cum in pussy', 'cum overflow', 'detailed pussy', 'detailed penis', 'pubic hair'
        }

        # 2. 태그 세척 및 정제
        import re
        def clean_tag(t):
            # (), [], {}, <> 및 가중치(:1.2) 제거
            t = t.strip().lower()
            # 괄호 제거
            t = re.sub(r'[\(\)\[\]\{\}]', '', t)
            # <lora:name:1.2> 처리 -> name
            if t.startswith('<lora:'):
                parts = t.split(':')
                return parts[1] if len(parts) > 1 else t
            # tag:1.2 처리
            if ':' in t:
                parts = t.split(':')
                # prefix:tag 형태인 경우 (예: artist:name)
                if any(p in t for p in ['artist', 'character', 'series', 'copyright']):
                    # prefix와 tag 둘 다 가져가되 가중치 숫자만 제거
                    return ":".join([p for p in parts if not re.match(r'^\d+(\.\d+)?$', p)])
                else:
                    # 그 외에는 첫 번째 일반 단어만 (예: blonde hair:1.1 -> blonde hair)
                    return parts[0]
            return t

        raw_tags = [t.strip() for t in prompt.split(',') if t.strip()]
        cleaned_tags = []
        for rt in raw_tags:
            ct = clean_tag(rt)
            # Junk 체크 (접두어 너머의 알맹이 확인)
            al = ct.split(':')[-1] if ':' in ct else ct
            if al in JUNK_TAGS:
                continue
            if len(al) < 3:
                continue
            cleaned_tags.append(ct)

        if not cleaned_tags:
            return []

        # 3. 우선순위 태그 선정 및 가중치 부여
        # Artist, Character, Series 등은 10점, 일반은 2점
        scored_tags = []
        for t in cleaned_tags:
            score = 2
            if any(p in t for p in ['artist', 'character', 'series', 'copyright', 'lora']):
                score = 10
            elif len(t.split()) >= 2: # 캐릭터 이름 등 두 단어 이상
                score = 5
            scored_tags.append((t, score))

        # 가중치 순으로 정렬하여 상위 10개 키워드 추출
        scored_tags.sort(key=lambda x: x[1], reverse=True)
        top_tags = scored_tags[:10]

        # 4. SQL 랭킹 쿼리 생성
        # SQLite에서 CASE WHEN을 사용하여 점수 합산
        score_cases = []
        sql_params = []
        for tag, score in top_tags:
            # tag:name 형태면 name만 검색에 사용 (유연성 확보)
            search_val = tag.split(':')[-1] if ':' in tag else tag
            score_cases.append(f"(CASE WHEN json_extract(metadata, '$.prompt') LIKE ? THEN {score} ELSE 0 END)")
            sql_params.append(f"%{search_val}%")

        score_expr = " + ".join(score_cases)
        sql = f"""
            SELECT no, filepath, platform, makeTime, is_favorite, ({score_expr}) as match_score
            FROM NAIimgInfo 
            WHERE no != ? AND match_score > 0
            ORDER BY match_score DESC, makeTime DESC
            LIMIT ?
        """
        sql_params.extend([image_id, limit])

        tag_results = cursor.execute(sql, sql_params).fetchall()
        return [dict(ix) for ix in tag_results]

    except Exception as e:
        print(f"Error in get_similar_images: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        conn.close()

if __name__ == '__main__':
    print("Initializing database...")
    init_db()

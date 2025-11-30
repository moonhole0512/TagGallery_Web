import sqlite3
import json

DB_FILE = "image_gallery.db"

def create_table_if_not_exists():
    """테이블이 존재하지 않으면 생성합니다."""
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
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error while ensuring table exists: {e}")
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
                           metadata TEXT)''')
        conn.commit()
        print("Database initialized successfully with the new schema.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환합니다."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
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

def get_images(page = 1, limit = 50, query = None, sort_by: str = "random", platform_filter: str = "all"):
    """
    이미지 목록을 페이지네이션하여 반환합니다. 태그 검색, 정렬 및 플랫폼 필터링을 지원합니다.
    """
    offset = (page - 1) * limit
    conn = get_db_connection()
    
    sql_parts = ["SELECT no, filepath, platform, makeTime FROM NAIimgInfo"]
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

    if where_clauses:
        sql_parts.append(" WHERE " + " AND ".join(where_clauses))
        count_sql_parts.append(" WHERE " + " AND ".join(where_clauses))

    # 정렬 옵션 처리
    if sort_by == "desc":
        sql_parts.append(" ORDER BY makeTime DESC")
    elif sort_by == "asc":
        sql_parts.append(" ORDER BY makeTime ASC")
    else: # "random" 또는 기본값
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
    image_dict['metadata'] = json.loads(image_dict['metadata'])
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
        # SQLite는 튜플 리스트를 IN 절에 직접 사용할 수 없으므로, 플레이스홀더를 사용합니다.
        placeholders = ','.join(['?' for _ in image_ids])
        select_sql = f"SELECT filepath FROM NAIimgInfo WHERE no IN ({placeholders})"
        file_records = cursor.execute(select_sql, image_ids).fetchall()
        
        for record in file_records:
            filepaths_to_delete.append(record['filepath'])
            
        # 이미지 레코드들을 삭제합니다.
        delete_sql = f"DELETE FROM NAIimgInfo WHERE no IN ({placeholders})"
        cursor.execute(delete_sql, image_ids)
        
        conn.commit()
        print(f"데이터베이스에서 {len(filepaths_to_delete)}개의 이미지 레코드를 삭제했습니다.")
        return filepaths_to_delete
    except sqlite3.Error as e:
        conn.rollback()
        print(f"데이터베이스 오류로 이미지 삭제에 실패했습니다: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    print("Initializing database...")
    init_db()

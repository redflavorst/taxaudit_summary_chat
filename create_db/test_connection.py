import psycopg2
import sys

# 인코딩 문제 해결을 위한 테스트
try:
    # 방법 1: 개별 파라미터로 연결
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="ragdb",
        user="postgres",
        password="root"
    )
    print("PostgreSQL 연결 성공!")
    
    # ragdb 데이터베이스가 없을 경우 생성
    conn.close()
    
except psycopg2.OperationalError as e:
    if "database" in str(e) and "does not exist" in str(e):
        print("ragdb 데이터베이스가 없습니다. postgres DB에 연결하여 생성합니다...")
        try:
            # postgres 기본 DB에 연결
            conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="postgres",
                user="postgres",
                password="root"
            )
            conn.set_isolation_level(0)  # autocommit 모드
            cur = conn.cursor()
            cur.execute("CREATE DATABASE ragdb")
            print("ragdb 데이터베이스 생성 완료!")
            cur.close()
            conn.close()
        except Exception as create_err:
            print(f"DB 생성 실패: {create_err}")
    else:
        print(f"연결 실패: {e}")
        print("\nPostgreSQL이 실행 중인지 확인하세요:")
        print("1. PostgreSQL 서비스가 시작되었는지 확인")
        print("2. 포트 5432가 사용 가능한지 확인")
        print("3. 사용자명과 비밀번호가 올바른지 확인")
        
except UnicodeDecodeError as e:
    print(f"인코딩 오류: {e}")
    print("config.py 파일의 인코딩을 확인하세요")
    
except Exception as e:
    print(f"기타 오류: {e}")
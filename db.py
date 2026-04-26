import pymysql
from pymysql.cursors import DictCursor
from werkzeug.security import generate_password_hash
from config import Config

# Get the config from the Config class
DB_CONFIG = Config.MYSQL_CONFIG

def get_db_connection():
    """Returns a MySQL connection object."""
    try:
        conn = pymysql.connect(
            **DB_CONFIG,
            cursorclass=DictCursor,
            autocommit=False,
        )
        return conn
    except Exception as e:
        print(f"ERROR: Unable to connect to MySQL database: {e}")
        return None

def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    """Generic function to execute a query and fetch data (if needed)."""
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(query, params)

            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()

            conn.commit()
            return True

    except Exception as e:
        print(f"Database Query Error: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def create_tables():
    """Creates all tables in MySQL, including the default Super Admin."""
    queries = [
        '''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            fullname TEXT NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role_access VARCHAR(255) NOT NULL,
            date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'Active'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            status VARCHAR(50) DEFAULT 'Active',
            role VARCHAR(50) DEFAULT 'student',
            date_registered TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS requests (
            id INT AUTO_INCREMENT PRIMARY KEY,
            requester_email VARCHAR(255) NOT NULL,
            lastname VARCHAR(255),
            firstname VARCHAR(255),
            email VARCHAR(255) NOT NULL,
            student_id VARCHAR(255),
            # contact VARCHAR(100),
            # birthdate VARCHAR(255),
            status VARCHAR(50) DEFAULT 'Pending' NOT NULL,
            # course_grade VARCHAR(255),
            year_entry VARCHAR(255),
            last_school VARCHAR(255),
            purpose TEXT,
            address TEXT,
            document VARCHAR(255),
            final_price DECIMAL(10, 2) DEFAULT 0.0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL DEFAULT NULL,
            assigned_admin_id INT NULL,
            delivery_method VARCHAR(255) DEFAULT 'Pick-up',
            document_file_path VARCHAR(500) NULL,
            verification_token VARCHAR(64) NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS request_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            request_id INT NOT NULL,
            admin_id INT NULL,
            status VARCHAR(50) NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS student_info (
            requester_email VARCHAR(255) PRIMARY KEY,
            lastname VARCHAR(255),
            firstname VARCHAR(255),
            middlename VARCHAR(255),
            suffix VARCHAR(100),
            gender VARCHAR(255),
            age INT,
            contact VARCHAR(100),
            birthdate VARCHAR(255),
            enrollment_status VARCHAR(255),
            education_level VARCHAR(255),
            track VARCHAR(100),
            course_grade VARCHAR(255),
            student_id VARCHAR(255),
            address TEXT,
            FOREIGN KEY(requester_email) REFERENCES users(email)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS document_types (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doc_name VARCHAR(255) UNIQUE NOT NULL,
            fee DECIMAL(10, 2) DEFAULT 0.0,
            education_level VARCHAR(255) DEFAULT 'All'
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            request_id INT UNIQUE NOT NULL,
            reference_no VARCHAR(255) NOT NULL,
            amount_paid DECIMAL(10, 2) NOT NULL,
            proof_image TEXT NOT NULL,
            payment_status VARCHAR(255) DEFAULT 'Pending Verification',
            date_uploaded TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES requests(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            message TEXT NOT NULL,
            category VARCHAR(50),
            admin_id INT,
            is_read SMALLINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES admin_users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
        '''
        CREATE TABLE IF NOT EXISTS student_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            message_text TEXT NOT NULL,
            is_read INT DEFAULT 0,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''',
    ]

    conn = get_db_connection()
    if conn is None:
        return
    try:
        cur = conn.cursor()
        for query in queries:
            cur.execute(query)
        conn.commit()
    except Exception as e:
        print(f"Error during table creation: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    # Migrate existing databases: add new columns if they don't exist
    migration_queries = [
        "ALTER TABLE student_info ADD COLUMN IF NOT EXISTS education_level VARCHAR(255) AFTER enrollment_status",
        "ALTER TABLE student_info ADD COLUMN IF NOT EXISTS track VARCHAR(100) AFTER education_level",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS document_file_path VARCHAR(500) NULL",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS verification_token VARCHAR(64) NULL",
        "ALTER TABLE requests ADD COLUMN IF NOT EXISTS rejection_reason TEXT NULL",
        "ALTER TABLE student_info ADD COLUMN IF NOT EXISTS gender VARCHAR(255) AFTER suffix",
        "ALTER TABLE document_types ADD COLUMN IF NOT EXISTS education_level VARCHAR(255) DEFAULT 'All'",
    ]
    conn2 = get_db_connection()
    if conn2:
        try:
            cur2 = conn2.cursor()
            for mq in migration_queries:
                cur2.execute(mq)
            conn2.commit()
        except Exception as e:
            print(f"Migration warning: {e}")
            conn2.rollback()
        finally:
            conn2.close()

    # Default Super Admin creation
    default_email = 'superadmin@thesis.com'
    admin_exists = execute_query("SELECT id FROM admin_users WHERE email = %s", (default_email,), fetch_one=True)
    
    if not admin_exists:
        default_password = generate_password_hash('admire_25.')
        insert_admin_query = "INSERT INTO admin_users (fullname, email, password_hash, role_access) VALUES (%s, %s, %s, %s)"
        execute_query(insert_admin_query, ('Super Admin', default_email, default_password, 'Super Admin'))
        print("\n!!! DEFAULT SUPER ADMIN CREATED: email=superadmin@thesis.com, password=admire_25. !!!\n")

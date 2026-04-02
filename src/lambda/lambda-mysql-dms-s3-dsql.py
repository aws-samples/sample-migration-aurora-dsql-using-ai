import json
import boto3
import logging
import pymysql
import psycopg2
import os
import uuid
import time
import csv
import gzip
from typing import Dict, Any, List

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# S3 and Aurora DSQL connection details
DSQL_SECRET_ARN = os.environ.get('DSQL_SECRET_ARN')
REGION = os.environ.get('AWS_REGION')

# UUID conversion feature flag
ENABLE_UUID_CONVERSION = os.environ.get('ENABLE_UUID_CONVERSION', 'false').lower() == 'true'

# Source database secret ARN for FK detection
SOURCE_DB_SECRET_ARN = os.environ.get('SOURCE_DB_SECRET_ARN')
SOURCE_DB_SCHEMA = os.environ.get('SOURCE_DB_SCHEMA', 'public')

# Retry configuration for OC001 errors
MAX_RETRIES = 3
RETRY_DELAY_MS = 100
MAX_RETRY_DELAY_MS = 2000

# Caches
pk_cache = {}
fk_cache = {}
source_db_credentials = None
source_db_credentials_timestamp = 0
source_pk_types_cache = {}
dsql_config = None
dsql_config_timestamp = 0

# Credential cache TTL (15 minutes)
CREDENTIALS_TTL = 900

# GLOBAL: Track which tables have had _original columns initialized
tables_initialized = set()

# Initialize DSQL config variables
DSQL_ENDPOINT = None
DATABASE_NAME = None
SCHEMA_NAME = None
USERNAME = None
UUID_NAMESPACE = None
BASE_NAMESPACE = None

# S3 client
s3_client = boto3.client('s3', region_name=REGION)

def get_dsql_config():
    """Get DSQL configuration from Secrets Manager with caching"""
    global dsql_config, dsql_config_timestamp, DSQL_ENDPOINT, DATABASE_NAME, SCHEMA_NAME, USERNAME, UUID_NAMESPACE, BASE_NAMESPACE
    
    if dsql_config and (time.time() - dsql_config_timestamp < CREDENTIALS_TTL):
        return dsql_config
    
    try:
        secrets_client = boto3.client('secretsmanager', region_name=REGION)
        response = secrets_client.get_secret_value(SecretId=DSQL_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        
        # Update global variables directly
        DSQL_ENDPOINT = secret['endpoint']
        DATABASE_NAME = secret['database']
        SCHEMA_NAME = secret['schema']
        USERNAME = secret.get('username', 'admin')
        UUID_NAMESPACE = secret.get('uuid_namespace', '6ba7b810-9dad-11d1-80b4-00c04fd430c8')
        
        try:
            BASE_NAMESPACE = uuid.UUID(UUID_NAMESPACE)
        except ValueError:
            logger.warning(f"Invalid UUID_NAMESPACE, using default")
            BASE_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
        
        dsql_config = secret
        dsql_config_timestamp = time.time()
        return dsql_config
        
    except Exception as e:
        logger.error(f"Error retrieving DSQL config: {str(e)}")
        raise

def is_oc001_error(error_msg: str) -> bool:
    """Check if error is OC001 (optimistic concurrency control)"""
    return 'OC001' in str(error_msg) or 'schema has been updated by another transaction' in str(error_msg).lower()

def retry_on_oc001(func):
    """Decorator to retry operations on OC001 errors with exponential backoff"""
    def wrapper(*args, **kwargs):
        last_error = None
        delay = RETRY_DELAY_MS / 1000.0
        
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if is_oc001_error(str(e)):
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(f"OC001 error on attempt {attempt + 1}, retrying in {delay}s: {str(e)}")
                        time.sleep(delay)
                        delay = min(delay * 2, MAX_RETRY_DELAY_MS / 1000.0)
                        continue
                    else:
                        logger.error(f"OC001 error after {MAX_RETRIES} attempts: {str(e)}")
                raise
        
        raise last_error
    return wrapper

def get_converted_pk_columns(table_name: str, token: str) -> List[str]:
    """Get list of PK columns that are integer in SOURCE but UUID in TARGET"""
    cache_key = f"{SOURCE_DB_SCHEMA}.{table_name}"
    
    if cache_key in source_pk_types_cache:
        return source_pk_types_cache[cache_key]
    
    if not ENABLE_UUID_CONVERSION or not SOURCE_DB_SECRET_ARN:
        return []
    
    try:
        # Get source integer PKs (MySQL syntax)
        source_conn = get_source_db_connection()
        source_cursor = source_conn.cursor()
        
        source_sql = """
        SELECT kcu.COLUMN_NAME
        FROM information_schema.TABLE_CONSTRAINTS tc
        JOIN information_schema.KEY_COLUMN_USAGE kcu 
            ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME 
            AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
        JOIN information_schema.COLUMNS c
            ON c.TABLE_SCHEMA = kcu.TABLE_SCHEMA
            AND c.TABLE_NAME = kcu.TABLE_NAME
            AND c.COLUMN_NAME = kcu.COLUMN_NAME
        WHERE tc.TABLE_SCHEMA = %s 
            AND tc.TABLE_NAME = %s 
            AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
            AND c.DATA_TYPE IN ('int', 'bigint', 'smallint', 'integer', 'tinyint', 'mediumint')
        """
        
        source_cursor.execute(source_sql, [SOURCE_DB_SCHEMA, table_name])
        source_integer_pks = {row[0] for row in source_cursor.fetchall()}
        source_cursor.close()
        source_conn.close()
        
        if not source_integer_pks:
            source_pk_types_cache[cache_key] = []
            return []
        
        # Get target UUID PKs (PostgreSQL syntax for DSQL)

        target_conn = get_dsql_connection(token)
        target_cursor = target_conn.cursor()
        
        target_sql = """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
            ON tc.constraint_name = kcu.constraint_name 
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.columns c
            ON c.table_schema = kcu.table_schema
            AND c.table_name = kcu.table_name
            AND c.column_name = kcu.column_name
        WHERE tc.table_schema = %s 
            AND tc.table_name = %s 
            AND tc.constraint_type = 'PRIMARY KEY'
            AND c.data_type = 'uuid'
        """
        
        target_cursor.execute(target_sql, [SCHEMA_NAME, table_name])
        target_uuid_pks = {row[0] for row in target_cursor.fetchall()}
        target_cursor.close()
        target_conn.close()
        
        converted_pks = list(source_integer_pks & target_uuid_pks)
        
        source_pk_types_cache[cache_key] = converted_pks
        logger.info(f"Table {table_name} has converted PKs (int→UUID): {converted_pks}")
        
        return converted_pks
        
    except Exception as e:
        logger.error(f"Error getting converted PK columns for {table_name}: {str(e)}")
        return []

def initialize_table_columns_once(table_name: str, token: str) -> None:
    """Initialize _original columns for a table ONCE per Lambda container lifecycle"""
    if not ENABLE_UUID_CONVERSION:
        return
    
    if table_name in tables_initialized:
        logger.info(f"Table {table_name} already initialized in this container")
        return
    
    conn = None
    cursor = None
    
    try:

        conn = get_dsql_connection(token)
        cursor = conn.cursor()
        
        converted_pk_columns = get_converted_pk_columns(table_name, token)
        
        if not converted_pk_columns:
            logger.info(f"Table {table_name} has no integer PKs converted to UUID, skipping _original columns")
            tables_initialized.add(table_name)
            return
        
        cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
        """, [SCHEMA_NAME, table_name])
        
        existing_columns = {row[0] for row in cursor.fetchall()}
        
        for pk in converted_pk_columns:
            col_name = f"{pk}_original"
            if col_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE {SCHEMA_NAME}."{table_name}" ADD COLUMN "{col_name}" INTEGER')
                    conn.commit()
                    logger.info(f"Added column {table_name}.{col_name}")
                except Exception as e:
                    error_msg = str(e).lower()
                    if 'already exists' in error_msg or 'duplicate column' in error_msg:
                        conn.rollback()
                        logger.info(f"Column {table_name}.{col_name} already exists")
                    else:
                        conn.rollback()
                        raise
        
        tables_initialized.add(table_name)
        logger.info(f"Table {table_name} initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing table {table_name}: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle S3 event triggered by DMS CSV file creation"""
    processed_records = 0
    failed_records = 0
    
    # Load DSQL configuration from Secrets Manager
    try:
        get_dsql_config()
    except Exception as e:
        logger.error(f"Failed to load DSQL configuration: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Config load failed'})}
    
    # Get DSQL auth token
    try:
        dsql_client = boto3.client('dsql', region_name=REGION)
        auth_token = dsql_client.generate_db_connect_admin_auth_token(
            Hostname=DSQL_ENDPOINT
        )
    except Exception as e:
        logger.error(f"Failed to generate DSQL auth token: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Auth failed'})}
    
    # Process S3 events
    for record in event['Records']:
        try:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            logger.info(f"Processing S3 file: s3://{bucket}/{key}")
            
            process_csv_file(bucket, key, auth_token)
            processed_records += 1
            
        except Exception as e:
            logger.error(f"Error processing S3 record: {str(e)}")
            failed_records += 1
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed_files': processed_records,
            'failed_files': failed_records
        })
    }

def process_csv_file(bucket: str, key: str, token: str) -> None:
    """Download and process CSV file from S3 with AddColumnName=true"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        
        if key.endswith('.gz'):
            file_content = gzip.decompress(response['Body'].read()).decode('utf-8')
        else:
            file_content = response['Body'].read().decode('utf-8')
        
        table_name = extract_table_name_from_key(key)
        
        if not table_name:
            logger.error(f"Could not extract table name from key: {key}")
            return
        
        initialize_table_columns_once(table_name, token)
        is_full_load = '/LOAD' in key or not 'cdc' in key
        
        # CSV has headers with AddColumnName=true
        csv_reader = csv.DictReader(file_content.splitlines())
        row_count = 0
        
        for row in csv_reader:
            if not row:
                continue
            
            # Get operation type and remove DMS metadata columns
            operation = row.get('Op', 'I')
            row_dict = {k: v for k, v in row.items() if not k.startswith('dms_') and k != 'Op'}
            
            # Convert empty strings to None and parse integers
            for k, v in row_dict.items():
                if v == '':
                    row_dict[k] = None
                elif v and v.lstrip('-').isdigit():
                    row_dict[k] = int(v)
            
            if is_full_load:
                process_full_load_row(table_name, row_dict, token)
            else:
                process_cdc_row(table_name, row_dict, operation, token)
            
            row_count += 1
        
        logger.info(f"Successfully processed {row_count} rows from {key}")
        
    except Exception as e:
        logger.error(f"Error processing CSV file {key}: {str(e)}")
        raise

def extract_table_name_from_key(key: str) -> str:
    """Extract table name from S3 key path"""
    parts = key.split('/')
    
    if 'cdc' in parts:
        cdc_idx = parts.index('cdc')
        if len(parts) > cdc_idx + 2:
            return parts[cdc_idx + 2]
    else:
        if len(parts) >= 3:
            return parts[-2]
    
    return None

@retry_on_oc001
def process_full_load_row(table_name: str, data: Dict[str, Any], token: str) -> None:
    """Process full load row"""
    if not data:
        return
    
    transformed_data = transform_with_original(table_name, data, token)
    
    columns = list(transformed_data.keys())
    values = list(transformed_data.values())
    placeholders = ', '.join(['%s' for _ in columns])
    column_names = ', '.join([f'"{col}"' for col in columns])
    
    sql = f'INSERT INTO {SCHEMA_NAME}."{table_name}" ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
    execute_dsql_query(sql, values, token)

def process_cdc_row(table_name: str, data: Dict[str, Any], operation: str, token: str) -> None:
    """Process CDC row based on operation type"""
    if operation == 'I':
        process_cdc_insert_row(table_name, data, token)
    elif operation == 'U':
        process_cdc_update_row(table_name, data, token)
    elif operation == 'D':
        process_cdc_delete_row(table_name, data, token)

@retry_on_oc001
def process_cdc_insert_row(table_name: str, data: Dict[str, Any], token: str) -> None:
    """Process CDC insert"""
    if not data:
        return
    
    transformed_data = transform_with_original(table_name, data, token)
    
    columns = list(transformed_data.keys())
    values = list(transformed_data.values())
    placeholders = ', '.join(['%s' for _ in columns])
    column_names = ', '.join([f'"{col}"' for col in columns])
    
    sql = f'INSERT INTO {SCHEMA_NAME}."{table_name}" ({column_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
    execute_dsql_query(sql, values, token)

@retry_on_oc001
def process_cdc_update_row(table_name: str, data: Dict[str, Any], token: str) -> None:
    """Process CDC update"""
    if not data:
        return
    
    transformed_data = transform_with_original(table_name, data, token)
    primary_keys = get_primary_keys(table_name, token)
    
    set_clauses = []
    set_values = []
    for col, val in transformed_data.items():
        if col not in primary_keys and not col.endswith('_original'):
            set_clauses.append(f'"{col}" = %s')
            set_values.append(val)
    
    where_clauses = []
    where_values = []
    for pk in primary_keys:
        pk_value = transformed_data.get(pk)
        if pk_value is not None:
            where_clauses.append(f'"{pk}" = %s')
            where_values.append(pk_value)
    
    if set_clauses and where_clauses:
        sql = f'UPDATE {SCHEMA_NAME}."{table_name}" SET {", ".join(set_clauses)} WHERE {" AND ".join(where_clauses)}'
        execute_dsql_query(sql, set_values + where_values, token)

@retry_on_oc001
def process_cdc_delete_row(table_name: str, data: Dict[str, Any], token: str) -> None:
    """Process CDC delete"""
    if not data:
        return
    
    transformed_data = transform_with_original(table_name, data, token)
    primary_keys = get_primary_keys(table_name, token)
    
    where_clauses = []
    where_values = []
    for pk in primary_keys:
        pk_value = transformed_data.get(pk)
        if pk_value is not None:
            where_clauses.append(f'"{pk}" = %s')
            where_values.append(pk_value)
    
    if where_clauses:
        sql = f'DELETE FROM {SCHEMA_NAME}."{table_name}" WHERE {" AND ".join(where_clauses)}'
        execute_dsql_query(sql, where_values, token)

def get_dsql_connection(token: str):
    """Connect to Aurora DSQL using psycopg2"""

    return psycopg2.connect(
        host=DSQL_ENDPOINT,
        port=5432,
        database=DATABASE_NAME,
        user=USERNAME,
        password=token,
        sslmode='require'
    )

def get_source_db_credentials():
    """Get source MySQL database credentials from Secrets Manager"""
    global source_db_credentials, source_db_credentials_timestamp
    
    if source_db_credentials and (time.time() - source_db_credentials_timestamp < CREDENTIALS_TTL):
        return source_db_credentials
    
    try:
        secrets_client = boto3.client('secretsmanager', region_name=REGION)
        response = secrets_client.get_secret_value(SecretId=SOURCE_DB_SECRET_ARN)
        secret = json.loads(response['SecretString'])
        
        source_db_credentials = {
            'host': secret.get('host'),
            'port': int(secret.get('port', 3306)),
            'database': secret.get('dbname') or secret.get('database'),
            'user': secret.get('username') or secret.get('user'),
            'password': secret.get('password')
        }
        
        source_db_credentials_timestamp = time.time()
        
        return source_db_credentials
        
    except Exception as e:
        logger.error(f"Error retrieving source DB credentials: {str(e)}")
        return None

def get_source_db_connection():
    """Connect to source MySQL database"""
    global source_db_credentials, source_db_credentials_timestamp
    
    creds = get_source_db_credentials()
    
    if not creds:
        raise ValueError("Unable to retrieve source database credentials")
    
    try:
        return pymysql.connect(
            host=creds['host'],
            port=creds['port'],
            database=creds['database'],
            user=creds['user'],
            password=creds['password'],
            ssl={'ssl': True}
        )
    except Exception as e:
        error_msg = str(e).lower()
        if 'access denied' in error_msg or 'authentication' in error_msg or 'password' in error_msg:
            logger.warning(f"Authentication failed, invalidating credential cache: {str(e)}")
            source_db_credentials = None
            source_db_credentials_timestamp = 0
        raise

def get_primary_keys(table_name: str, token: str) -> List[str]:
    if table_name in pk_cache:
        return pk_cache[table_name]
    
    try:

        sql = """
        SELECT column_name 
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu 
        ON tc.constraint_name = kcu.constraint_name 
        AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = %s 
        AND tc.table_name = %s 
        AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
        
        conn = get_dsql_connection(token)
        cursor = conn.cursor()
        cursor.execute(sql, [SCHEMA_NAME, table_name])
        
        primary_keys = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        if not primary_keys:
            error_msg = "No primary key found for table"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        pk_cache[table_name] = primary_keys
        
        return primary_keys
        
    except Exception as e:
        logger.error(f"Error getting primary keys for {table_name}: {str(e)}")
        raise

def get_foreign_keys(table_name: str, token: str) -> Dict[str, str]:
    """Get foreign key columns and their referenced tables from SOURCE MySQL database"""
    cache_key = f"{SOURCE_DB_SCHEMA}.{table_name}"
    
    if cache_key in fk_cache:
        return fk_cache[cache_key]
    
    if not ENABLE_UUID_CONVERSION:
        return {}
    
    try:
        source_conn = get_source_db_connection()
        cursor = source_conn.cursor()
        
        # MySQL syntax for foreign keys
        sql = """
        SELECT 
            kcu.COLUMN_NAME,
            kcu.REFERENCED_TABLE_NAME
        FROM information_schema.TABLE_CONSTRAINTS AS tc 
        JOIN information_schema.KEY_COLUMN_USAGE AS kcu
            ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
            AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
        WHERE tc.CONSTRAINT_TYPE = 'FOREIGN KEY' 
            AND tc.TABLE_SCHEMA = %s
            AND tc.TABLE_NAME = %s
        """
        
        cursor.execute(sql, [SOURCE_DB_SCHEMA, table_name])
        fk_map = {row[0]: row[1] for row in cursor.fetchall()}
        
        cursor.close()
        source_conn.close()
        
        fk_cache[cache_key] = fk_map
        
        return fk_map
        
    except Exception as e:
        logger.error(f"Error getting foreign keys from source for {table_name}: {str(e)}")
        return {}

def int_to_uuid(table_name: str, int_id: int) -> str:
    """Convert integer to deterministic UUID"""
    if int_id is None:
        return None
    namespace = uuid.uuid5(BASE_NAMESPACE, table_name)
    return str(uuid.uuid5(namespace, str(int_id)))

def transform_with_original(table_name: str, data: Dict[str, Any], token: str) -> Dict[str, Any]:
    """Transform integer IDs to UUIDs and keep original values"""
    if not ENABLE_UUID_CONVERSION:
        return data
    
    transformed = {}
    
    try:
        pk_columns = get_primary_keys(table_name, token)
        converted_pk_columns = get_converted_pk_columns(table_name, token)
        fk_map = get_foreign_keys(table_name, token)
        
        for key, value in data.items():
            if value is not None and isinstance(value, int):
                if key in converted_pk_columns:
                    transformed[key] = int_to_uuid(table_name, value)
                    transformed[f'{key}_original'] = value
                elif key in fk_map:
                    ref_table = fk_map[key]
                    ref_converted_pks = get_converted_pk_columns(ref_table, token)
                    if ref_converted_pks:
                        transformed[key] = int_to_uuid(ref_table, value)
                    else:
                        transformed[key] = value
                else:
                    transformed[key] = value
            else:
                transformed[key] = value
        
        return transformed
        
    except Exception as e:
        logger.error(f"Error in UUID transformation: {str(e)}")
        return data

        execute_dsql_query(sql, where_values, token)

@retry_on_oc001
def execute_dsql_query(sql: str, parameters: List[Any] = None, token: str = None) -> None:
    conn = None
    cursor = None
    
    try:

        conn = get_dsql_connection(token)
        cursor = conn.cursor()
        
        if parameters:
            cursor.execute(sql, parameters)
        else:
            cursor.execute(sql)
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"SQL error: {str(e)}")
        if conn:
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

import json
import boto3
import psycopg2
import os
from typing import Dict, Any, List

# Environment variables
DMS_TASK_ARN = os.environ['DMS_TASK_ARN']
SOURCE_SECRET_ARN = os.environ['SOURCE_SECRET_ARN']
DSQL_SECRET_ARN = os.environ['DSQL_SECRET_ARN']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
SOURCE_SCHEMA = os.environ.get('SOURCE_SCHEMA', 'public')

# Initialize DSQL config variables
DSQL_ENDPOINT = None
DSQL_USERNAME = None
DSQL_DATABASE = None
DSQL_SCHEMA = None

def get_dsql_config():
    """Get DSQL configuration from Secrets Manager"""
    global DSQL_ENDPOINT, DSQL_USERNAME, DSQL_DATABASE, DSQL_SCHEMA
    
    secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
    response = secrets_client.get_secret_value(SecretId=DSQL_SECRET_ARN)
    secret = json.loads(response['SecretString'])
    
    DSQL_ENDPOINT = secret['endpoint']
    DSQL_DATABASE = secret['database']
    DSQL_SCHEMA = secret['schema']
    DSQL_USERNAME = secret.get('username', 'admin')

def lambda_handler(event, context):
    # Load DSQL configuration
    try:
        get_dsql_config()
    except Exception as e:
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': 'POST',
                'httpStatusCode': 500,
                'responseBody': {
                    'TEXT': {
                        'body': json.dumps({"error": f"Config load failed: {str(e)}"})
                    }
                }
            }
        }
    
    try:
        # Debug: Log the incoming event
        print(f"DEBUG - Received event: {json.dumps(event)}")
        
        # Parse Bedrock agent input
        action = event.get('actionGroup', '')
        function_name = event.get('function', '')
        api_path = event.get('apiPath', '')
        parameters = event.get('parameters', [])
        
        print(f"DEBUG - Parsed: actionGroup={action}, function={function_name}, apiPath={api_path}")
        
        # If function is empty, try to derive from apiPath
        if not function_name and api_path:
            path_to_function = {
                '/start-dms': 'start_dms_task',
                '/stop-dms': 'stop_dms_task', 
                '/check-status': 'check_dms_status',
                '/validate-data': 'validate_data'
            }
            function_name = path_to_function.get(api_path, '')
            print(f"DEBUG - Derived function from apiPath: {function_name}")
        
        # Convert parameters to dict
        params = {p['name']: p['value'] for p in parameters}
        
        # Also check requestBody for parameters (Bedrock agent format)
        request_body = event.get('requestBody', {})
        if request_body:
            content = request_body.get('content', {})
            json_content = content.get('application/json', {})
            properties = json_content.get('properties', [])
            for prop in properties:
                if isinstance(prop, dict) and 'name' in prop and 'value' in prop:
                    params[prop['name']] = prop['value']
        
        if function_name == 'start_dms_task':
            start_type = params.get('start_type', 'restart')  # Default to restart
            result = start_dms_task(start_type)
        elif function_name == 'stop_dms_task':
            result = stop_dms_task()
        elif function_name == 'check_dms_status':
            result = check_dms_status()
        elif function_name == 'validate_data':
            table_name = params.get('table_name')  # No default, None if not specified
            source_database = params.get('source_database')  # User can specify source DB
            result = validate_data(table_name, source_database)
        else:
            result = {"error": f"Unknown function: {function_name}"}
        
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action,
                'apiPath': api_path,
                'httpMethod': 'POST',
                'httpStatusCode': 200,
                'responseBody': {
                    'TEXT': {
                        'body': json.dumps(result)
                    }
                }
            }
        }
    except Exception as e:
        print(f"ERROR - Exception: {str(e)}")
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', ''),
                'apiPath': event.get('apiPath', ''),
                'httpMethod': 'POST',
                'httpStatusCode': 500,
                'responseBody': {
                    'TEXT': {
                        'body': json.dumps({"error": str(e)})
                    }
                }
            }
        }

def start_dms_task(start_type='restart'):
    try:
        dms_client = boto3.client('dms', region_name=AWS_REGION)
        
        # Check current status
        response = dms_client.describe_replication_tasks(
            Filters=[{'Name': 'replication-task-arn', 'Values': [DMS_TASK_ARN]}]
        )
        
        if not response['ReplicationTasks']:
            return {"error": "DMS task not found"}
        
        task = response['ReplicationTasks'][0]
        status = task['Status']
        
        if status == 'running':
            return {"message": "DMS task is already running", "status": status}
        elif status in ['stopped', 'failed', 'ready']:
            # Determine start type based on user request
            if start_type.lower() in ['restart', 'reload','start']:
                start_task_type = 'reload-target'
                action_message = "restarted with full reload"
            elif start_type.lower() in ['resume', 'continue']:
                start_task_type = 'resume-processing'
                action_message = "resumed from last position"
            else:  # Default to restart for any other input
                start_task_type = 'reload-target'
                action_message = "restarted with full reload (default)"
            
            # Start the task
            dms_client.start_replication_task(
                ReplicationTaskArn=DMS_TASK_ARN,
                StartReplicationTaskType=start_task_type
            )
            return {
                "message": f"DMS task {action_message} successfully", 
                "status": "starting",
                "start_type": start_task_type
            }
        else:
            return {"message": f"DMS task is in {status} state, cannot start"}
            
    except Exception as e:
        return {"error": f"Failed to start DMS task: {str(e)}"}

def stop_dms_task():
    try:
        dms_client = boto3.client('dms', region_name=AWS_REGION)
        
        # Check current status
        response = dms_client.describe_replication_tasks(
            Filters=[{'Name': 'replication-task-arn', 'Values': [DMS_TASK_ARN]}]
        )
        
        if not response['ReplicationTasks']:
            return {"error": "DMS task not found"}
        
        task = response['ReplicationTasks'][0]
        status = task['Status']
        
        if status == 'stopped':
            return {"message": "DMS task is already stopped", "status": status}
        elif status == 'running':
            # Stop the task
            dms_client.stop_replication_task(ReplicationTaskArn=DMS_TASK_ARN)
            return {"message": "DMS task stopped successfully", "status": "stopping"}
        else:
            return {"message": f"DMS task is in {status} state, cannot stop"}
            
    except Exception as e:
        return {"error": f"Failed to stop DMS task: {str(e)}"}

def check_dms_status():
    try:
        dms_client = boto3.client('dms', region_name=AWS_REGION)
        
        # Check current status
        response = dms_client.describe_replication_tasks(
            Filters=[{'Name': 'replication-task-arn', 'Values': [DMS_TASK_ARN]}]
        )
        
        if not response['ReplicationTasks']:
            return {"error": "DMS task not found"}
        
        task = response['ReplicationTasks'][0]
        status = task['Status']
        
        # Get task statistics if available
        stats = task.get('ReplicationTaskStats', {})
        
        return {
            "task_status": status,
            "task_identifier": task.get('ReplicationTaskIdentifier'),
            "migration_type": task.get('MigrationType'),
            "full_load_progress": stats.get('FullLoadProgressPercent', 0),
            "tables_loaded": stats.get('TablesLoaded', 0),
            "tables_loading": stats.get('TablesLoading', 0),
            "tables_queued": stats.get('TablesQueued', 0),
            "tables_errored": stats.get('TablesErrored', 0),
            "message": f"DMS task is currently {status}"
        }
            
    except Exception as e:
        return {"error": f"Failed to check DMS task status: {str(e)}"}

def create_validation_table_if_not_exists(dsql_conn):
    # Create validation table if it doesn't exist
    dsql_cursor = dsql_conn.cursor()
    dsql_cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_results (
            schema_name VARCHAR(255),
            table_name VARCHAR(255),
            primary_key_value VARCHAR(255),
            column_name VARCHAR(255),
            source_value TEXT,
            target_value TEXT,
            validation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (schema_name, table_name, primary_key_value, column_name, validation_timestamp)
        )
    """)
    dsql_conn.commit()
    dsql_cursor.close()


def validate_data(table_name: str = None, source_database: str = None):
    try:
        # Get source connection details from Secrets Manager
        secrets_client = boto3.client('secretsmanager', region_name=AWS_REGION)
        secret_response = secrets_client.get_secret_value(SecretId=SOURCE_SECRET_ARN)
        source_creds = json.loads(secret_response['SecretString'])
        
        # Use source database from user input, secrets, or environment variable
        db_name = source_database or source_creds.get('database') or source_creds.get('dbname')
        if not db_name:
            return {"error": "Source database name not found in secrets or user input"}
        
        # Connect to source database (PostgreSQL)
        source_conn = psycopg2.connect(
            host=source_creds['host'],
            user=source_creds['username'],
            password=source_creds['password'],
            database=db_name,
            port=int(source_creds.get('port', 5432))
        )
        
        # Get DSQL auth token
        dsql_client = boto3.client('dsql', region_name=AWS_REGION)
        auth_token = dsql_client.generate_db_connect_admin_auth_token(
            Hostname=DSQL_ENDPOINT
        )
        
        # Connect to DSQL
        dsql_conn = psycopg2.connect(
            host=DSQL_ENDPOINT,
            port=5432,
            database=DSQL_DATABASE,
            user=DSQL_USERNAME,
            password=auth_token,
            sslmode='require'
        )

        # Create validation table if needed
        create_validation_table_if_not_exists(dsql_conn)
        
        if table_name:
            # Validate specific table
            validation_result = compare_table_data(source_conn, dsql_conn, table_name, db_name)
        else:
            # Validate all tables in schema
            validation_result = validate_all_tables(source_conn, dsql_conn, SOURCE_SCHEMA, db_name)
        
        source_conn.close()
        dsql_conn.close()
        
        return validation_result
        
    except Exception as e:
        return {"error": f"Failed to validate data: {str(e)}"}

def get_target_column_type(dsql_cursor, table_name: str, column_name: str):
    """Get the data type of a column in the target DSQL table"""
    dsql_cursor.execute("""
        SELECT data_type 
        FROM information_schema.columns 
        WHERE table_schema = %s 
        AND table_name = %s 
        AND column_name = %s
    """, (DSQL_SCHEMA, table_name, column_name))
    result = dsql_cursor.fetchone()
    return result[0] if result else None

def compare_table_data(source_conn, dsql_conn, table_name: str, source_db: str):
    try:
        source_cursor = source_conn.cursor()
        dsql_cursor = dsql_conn.cursor()
        
        # Get row counts
        source_cursor.execute(f'SELECT COUNT(*) FROM "{SOURCE_SCHEMA}"."{table_name}"')
        source_count = source_cursor.fetchone()[0]
        dsql_cursor.execute(f'SELECT COUNT(*) FROM "{DSQL_SCHEMA}"."{table_name}"')
        dsql_count = dsql_cursor.fetchone()[0]
        
        # Get primary key column(s) from source
        source_cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
            AND i.indisprimary
            ORDER BY a.attnum
        """, (f"{SOURCE_SCHEMA}.{table_name}",))
        pk_columns = [row[0] for row in source_cursor.fetchall()]
        
        if not pk_columns:
            return {"error": f"No primary key found for table {table_name}"}
        
        # Check if PK columns are UUID in target (converted from integer)
        pk_is_uuid = {}
        for pk_col in pk_columns:
            target_type = get_target_column_type(dsql_cursor, table_name, pk_col)
            pk_is_uuid[pk_col] = (target_type == 'uuid')
        
        # Get all column names and types from source
        source_cursor.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns 
            WHERE table_schema = '{SOURCE_SCHEMA}' 
            AND table_name = '{table_name}'
            ORDER BY ordinal_position
        """)
        source_columns_info = source_cursor.fetchall()
        all_columns = [col[0] for col in source_columns_info]
        source_col_types = {col[0]: col[1] for col in source_columns_info}
        
        # Identify UUID-converted columns in target
        uuid_converted_cols = set()
        for col in all_columns:
            target_type = get_target_column_type(dsql_cursor, table_name, col)
            source_type = source_col_types.get(col, '')
            # If source is integer/bigint and target is UUID, it's converted
            if target_type == 'uuid' and source_type in ('integer', 'bigint', 'smallint'):
                uuid_converted_cols.add(col)
        
        # Column value validation
        column_mismatches = []
        if source_count == dsql_count and source_count > 0:
            # Build column lists for source query
            pk_list_src = ', '.join([f'"{col}"' for col in pk_columns])
            col_list_src = ', '.join([f'"{col}"' for col in all_columns])
            
            source_cursor.execute(f"""
                SELECT {col_list_src} 
                FROM "{SOURCE_SCHEMA}"."{table_name}" 
                ORDER BY {pk_list_src} 
                LIMIT 1000
            """)
            source_rows = source_cursor.fetchall()
            
            # Build column lists for target query - use _original columns for UUID-converted PKs
            target_pk_cols = []
            for pk_col in pk_columns:
                if pk_is_uuid.get(pk_col):
                    target_pk_cols.append(f'"{pk_col}_original"')
                else:
                    target_pk_cols.append(f'"{pk_col}"')
            pk_list_tgt = ', '.join(target_pk_cols)
            
            # For SELECT, use original columns only for UUID-converted PKs
            target_select_cols = []
            for col in all_columns:
                if col in uuid_converted_cols and col in pk_columns:
                    # PK has _original column
                    target_select_cols.append(f'"{col}_original"')
                elif col in uuid_converted_cols:
                    # Non-PK UUID column - skip validation
                    target_select_cols.append('NULL')
                else:
                    target_select_cols.append(f'"{col}"')
            col_list_tgt = ', '.join(target_select_cols)
            
            dsql_cursor.execute(f"""
                SELECT {col_list_tgt} 
                FROM "{DSQL_SCHEMA}"."{table_name}" 
                ORDER BY {pk_list_tgt} 
                LIMIT 1000
            """)
            dsql_rows = dsql_cursor.fetchall()
            
            # Compare row by row - skip UUID-converted columns in validation
            for i, (source_row, dsql_row) in enumerate(zip(source_rows, dsql_rows)):
                for j, (source_val, dsql_val) in enumerate(zip(source_row, dsql_row)):
                    col_name = all_columns[j]
                    
                    # Skip validation for all UUID-converted columns
                    if col_name in uuid_converted_cols:
                        continue
                    
                    if str(source_val) != str(dsql_val):
                        # Get primary key value for reporting
                        if len(pk_columns) == 1:
                            pk_index = all_columns.index(pk_columns[0])
                            row_id = source_row[pk_index]
                        else:
                            pk_values = []
                            for pk_col in pk_columns:
                                pk_index = all_columns.index(pk_col)
                                pk_values.append(str(source_row[pk_index]))
                            row_id = f"({', '.join(pk_values)})"
                        
                        column_mismatches.append({
                            "row": row_id,
                            "column": col_name,
                            "source_value": str(source_val),
                            "target_value": str(dsql_val)
                        })

        # Insert mismatches into validation table
        if column_mismatches:
            for mismatch in column_mismatches:
                dsql_cursor.execute("""
                    INSERT INTO validation_results
                    (schema_name, table_name, primary_key_value, column_name, source_value, target_value)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    DSQL_SCHEMA,
                    table_name,
                    str(mismatch['row']),
                    mismatch['column'],
                    mismatch['source_value'],
                    mismatch['target_value']
                ))
            dsql_conn.commit()
        
        source_cursor.close()
        dsql_cursor.close()
        
        result = {
            "table_name": table_name,
            "source_database": source_db,
            "source_count": source_count,
            "target_count": dsql_count,
            "count_match": source_count == dsql_count,
            "primary_keys": pk_columns,
            "uuid_converted_columns": list(uuid_converted_cols),
            "columns_validated": len(all_columns) - len(uuid_converted_cols),
            "columns_skipped": len(uuid_converted_cols),
            "column_mismatches": column_mismatches,
            "column_mismatches_count": len(column_mismatches)
        }
        
        if source_count != dsql_count:
            result["mismatch"] = f"Row count mismatch: source={source_count}, target={dsql_count}"
        elif column_mismatches:
            result["mismatch"] = f"Column value mismatches found: {len(column_mismatches)} differences"
        else:
            result["status"] = "Data validation passed - source and target match"
        
        return result
        
    except Exception as e:
        # Rollback on error to prevent transaction abort
        try:
            dsql_conn.rollback()
        except:
            pass
        return {"error": f"Failed to compare table data: {str(e)}"}

def validate_all_tables(source_conn, dsql_conn, source_schema: str, source_db: str):
    try:
        source_cursor = source_conn.cursor()
        dsql_cursor = dsql_conn.cursor()
        
        # Get all tables in the source database (schema)
        source_cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
        AND table_type = 'BASE TABLE'
        """, (source_schema,))
        tables = [row[0] for row in source_cursor.fetchall()]
        
        if not tables:
            return {"error": f"No tables found in {source_schema} schema"}
        
        results = {
            "source_database": source_db,
            "source_schema": source_schema,
            "target_schema": DSQL_SCHEMA,
            "total_tables": len(tables),
            "tables_validated": 0,
            "tables_matched": 0,
            "tables_mismatched": 0,
            "validation_details": {},
            "summary": ""
        }
        
        for table in tables:
            try:
                table_result = compare_table_data(source_conn, dsql_conn, table, source_db)
                results["validation_details"][table] = table_result
                results["tables_validated"] += 1
                
                if table_result.get("count_match") and table_result.get("column_mismatches_count", 0) == 0:
                    results["tables_matched"] += 1
                else:
                    results["tables_mismatched"] += 1
                    
            except Exception as e:
                # Rollback failed transaction
                dsql_conn.rollback()
                results["validation_details"][table] = {"error": str(e)}
                results["tables_mismatched"] += 1
        
        # Generate summary
        if results["tables_mismatched"] == 0:
            results["summary"] = f"All {results['tables_validated']} tables validated successfully - source and target match"
        else:
            results["summary"] = f"{results['tables_matched']} tables match, {results['tables_mismatched']} tables have mismatches"
        
        source_cursor.close()
        dsql_cursor.close()
        
        return results
        
    except Exception as e:
        return {"error": f"Failed to validate all tables: {str(e)}"}
import json
import pymysql
import boto3
import os

def get_source_connection(database_name=None):
    """Get source database connection using environment variable"""
    secret_arn = os.environ.get('SOURCE_SECRET_ARN')
    if not secret_arn:
        raise ValueError("SOURCE_SECRET_ARN environment variable not set")
    
    secrets_client = boto3.client('secretsmanager')
    secret = secrets_client.get_secret_value(SecretId=secret_arn)
    secret_data = json.loads(secret['SecretString'])
    
    return pymysql.connect(
        host=secret_data.get('host'),
        user=secret_data.get('username'),
        password=secret_data.get('password'),
        port=secret_data.get('port', 3306),
        database=database_name,
        connect_timeout=10
    )

def get_user_databases():
    """Get list of user databases excluding system databases"""
    try:
        conn = get_source_connection()
        cursor = conn.cursor()
        
        cursor.execute("SHOW DATABASES")
        all_databases = [db[0] for db in cursor.fetchall()]
        
        system_databases = ['information_schema', 'performance_schema', 'mysql', 'sys']
        user_databases = [db for db in all_databases if db not in system_databases]
        
        cursor.close()
        conn.close()
        
        return user_databases
    except Exception as e:
        return []

def extract_database_ddl(database_name):
    """Extract DDL statements from a database"""
    try:
        conn = get_source_connection(database_name)
        cursor = conn.cursor()
        
        # Extract tables
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        
        ddl_statements = []
        table_info = []
        
        for table in tables:
            cursor.execute(f"SHOW CREATE TABLE {table}")
            create_statement = cursor.fetchone()[1]
            ddl_statements.append(create_statement)
            
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]
            table_info.append({'table': table, 'rows': row_count})
        
        # Extract stored procedures
        cursor.execute("SHOW PROCEDURE STATUS WHERE Db = %s", (database_name,))
        procedures = cursor.fetchall()
        procedure_ddl = []
        
        for proc in procedures:
            proc_name = proc[1]
            cursor.execute(f"SHOW CREATE PROCEDURE {proc_name}")
            proc_ddl = cursor.fetchone()[2]
            procedure_ddl.append(proc_ddl)
        
        # Extract functions
        cursor.execute("SHOW FUNCTION STATUS WHERE Db = %s", (database_name,))
        functions = cursor.fetchall()
        function_ddl = []
        
        for func in functions:
            func_name = func[1]
            cursor.execute(f"SHOW CREATE FUNCTION {func_name}")
            func_ddl = cursor.fetchone()[2]
            function_ddl.append(func_ddl)
        
        # Extract triggers
        cursor.execute("SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS WHERE TRIGGER_SCHEMA = %s", (database_name,))
        triggers = cursor.fetchall()
        trigger_ddl = []
        
        for trigger in triggers:
            trigger_name = trigger[0]
            cursor.execute(f"SHOW CREATE TRIGGER {trigger_name}")
            trig_ddl = cursor.fetchone()[2]
            trigger_ddl.append(trig_ddl)
        
        # Extract indexes
        index_info = []
        for table in tables:
            cursor.execute(f"SHOW INDEX FROM {table}")
            indexes = cursor.fetchall()
            for idx in indexes:
                index_info.append({
                    'table': table,
                    'index_name': idx[2],
                    'column': idx[4],
                    'index_type': idx[10] if len(idx) > 10 else 'BTREE'
                })
        
        cursor.close()
        conn.close()
        
        return {
            'database': database_name,
            'tables_count': len(tables),
            'table_info': table_info,
            'procedures_count': len(procedures),
            'functions_count': len(functions),
            'triggers_count': len(triggers),
            'indexes_count': len(index_info),
            'ddl_statements': ddl_statements,
            'procedure_ddl': procedure_ddl,
            'function_ddl': function_ddl,
            'trigger_ddl': trigger_ddl,
            'index_info': index_info
        }
        
    except Exception as e:
        return {
            'database': database_name,
            'error': f'Failed to extract DDL: {str(e)}'
        }

def lambda_handler(event, context):
    """Handle both Bedrock Agent and direct AgentCore invocation requests"""
    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')
    http_method = event.get('httpMethod', '')
    
    if api_path == '/analyze-databases' and http_method == 'POST':
        request_body = event.get('requestBody', {})
        content = request_body.get('content', {})
        application_json = content.get('application/json', {})
        
        # Parse properties from different payload structures
        properties = {}
        if isinstance(application_json, dict):
            properties = application_json.get('properties', {})
            # Handle array of properties (AgentCore format)
            if isinstance(properties, list):
                # Convert list of {name, value} to dict
                properties = {prop.get('name'): prop.get('value') for prop in properties if isinstance(prop, dict)}
        elif isinstance(application_json, list) and len(application_json) > 0:
            properties = application_json[0] if isinstance(application_json[0], dict) else {}
        
        databases = properties.get('databases') if isinstance(properties, dict) else None
        
        if databases is None:
            databases = get_user_databases()
        elif isinstance(databases, str):
            databases = [databases]
        
        results = []
        summary = {
            'total_databases': len(databases),
            'successful_extractions': 0,
            'failed_extractions': 0,
            'total_tables': 0,
            'total_procedures': 0,
            'total_functions': 0,
            'total_triggers': 0,
            'total_indexes': 0,
            'user_databases_found': databases
        }
        
        for database_name in databases:
            extraction = extract_database_ddl(database_name)
            results.append(extraction)
            
            if 'error' not in extraction:
                summary['successful_extractions'] += 1
                summary['total_tables'] += extraction['tables_count']
                summary['total_procedures'] += extraction['procedures_count']
                summary['total_functions'] += extraction['functions_count']
                summary['total_triggers'] += extraction['triggers_count']
                summary['total_indexes'] += extraction['indexes_count']
            else:
                summary['failed_extractions'] += 1
        
        response_body = {
            'summary': summary,
            'database_extractions': results
        }
        
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': action_group,
                'apiPath': api_path,
                'httpMethod': http_method,
                'httpStatusCode': 200,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps(response_body)
                    }
                }
            }
        }
    
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': 404,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'error': 'Operation not supported'})
                }
            }
        }
    }

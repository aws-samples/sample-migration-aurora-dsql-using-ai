import json
import boto3
import psycopg2
import os
import re

def get_db_connection():
    """Get PostgreSQL database connection using credentials from Secrets Manager"""
    secrets_client = boto3.client('secretsmanager')
    secret_arn = os.environ['POSTGRESQL_SECRET_ARN']
    secret = json.loads(secrets_client.get_secret_value(SecretId=secret_arn)['SecretString'])
    
    return psycopg2.connect(
        host=secret['host'],
        user=secret['username'],
        password=secret['password'],
        database=secret.get('database'),
        port=int(secret.get('port', 5432))
    ), secret

def extract_postgresql_ddl(database_name, specific_tables=None):
    """Extract DDL statements from PostgreSQL database"""
    connection, secret = get_db_connection()
    
    schema = secret.get('schema', 'public')
    
    if database_name:
        connection.close()
        connection = psycopg2.connect(
            host=secret['host'],
            user=secret['username'],
            password=secret['password'],
            database=database_name,
            port=int(secret.get('port', 5432))
        )
    
    cursor = connection.cursor()
    ddls = {}

    # Get tables
    if specific_tables:
        table_query = f"""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE'
            AND table_name = ANY(%s)
        """
        cursor.execute(table_query, (specific_tables,))
    else:
        cursor.execute(f"""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = '{schema}' AND table_type = 'BASE TABLE'
        """)

    tables = [row[0] for row in cursor.fetchall()]

    # Get table DDLs
    for table in tables:
        cursor.execute(f"""
            SELECT 
                'CREATE TABLE ' || n.nspname || '.' || c.relname || ' (' ||
                string_agg(
                    a.attname || ' ' || 
                    pg_catalog.format_type(a.atttypid, a.atttypmod) ||
                    CASE 
                        WHEN a.attnotnull THEN ' NOT NULL'
                        ELSE ''
                    END ||
                    CASE 
                        WHEN ad.adbin IS NOT NULL THEN ' DEFAULT ' || pg_get_expr(ad.adbin, ad.adrelid)
                        ELSE ''
                    END,
                    ', ' ORDER BY a.attnum
                ) || 
                CASE 
                    WHEN pk.constraint_name IS NOT NULL THEN 
                        ', PRIMARY KEY (' || string_agg(DISTINCT pk.column_name, ', ') || ')'
                    ELSE ''
                END ||
                ');'
            FROM pg_attribute a
            JOIN pg_class c ON a.attrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
            LEFT JOIN (
                SELECT kcu.column_name, kcu.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'PRIMARY KEY' AND kcu.table_name = '{table}'
            ) pk ON pk.table_name = c.relname
            WHERE c.relname = '{table}' AND n.nspname = '{schema}' AND a.attnum > 0
            GROUP BY n.nspname, c.relname, pk.constraint_name
        """)
        result = cursor.fetchone()
        if result:
            ddls[f"table_{table}"] = result[0]

    # Get functions
    cursor.execute(f"""
        SELECT routine_name, routine_definition 
        FROM information_schema.routines 
        WHERE routine_schema = '{schema}' AND routine_type = 'FUNCTION'
    """)
    functions = cursor.fetchall()

    for func_name, func_def in functions:
        if func_def:
            cursor.execute(f"""
                SELECT pg_get_functiondef(p.oid) as function_ddl
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = '{schema}' AND p.proname = '{func_name}'
            """)
            complete_ddl = cursor.fetchone()
            ddls[f"function_{func_name}"] = complete_ddl[0] if complete_ddl else func_def
        else:
            ddls[f"function_{func_name}"] = f"-- Function: {func_name}"

    # Get triggers
    cursor.execute(f"""
        SELECT trigger_name, event_manipulation, event_object_table, action_statement
        FROM information_schema.triggers 
        WHERE trigger_schema = '{schema}'
    """)
    triggers = cursor.fetchall()

    for trigger_name, event, table, action in triggers:
        cursor.execute(f"""
            SELECT pg_get_triggerdef(t.oid) as trigger_ddl
            FROM pg_trigger t
            JOIN pg_class c ON t.tgrelid = c.oid
            JOIN pg_namespace n ON c.relnamespace = n.oid
            WHERE n.nspname = '{schema}' AND t.tgname = '{trigger_name}'
        """)
        complete_ddl = cursor.fetchone()
        ddls[f"trigger_{trigger_name}"] = complete_ddl[0] if complete_ddl else f"-- Trigger: {trigger_name} ON {table} {event}: {action}"

    # Get views
    cursor.execute(f"""
        SELECT table_name, view_definition 
        FROM information_schema.views 
        WHERE table_schema = '{schema}'
    """)
    views = cursor.fetchall()

    for view_name, view_def in views:
        ddls[f"view_{view_name}"] = f"CREATE VIEW {view_name} AS {view_def}"

    # Get indexes
    cursor.execute(f"""
        SELECT 
            schemaname, tablename, indexname, indexdef
        FROM pg_indexes 
        WHERE schemaname = '{schema}' 
        AND indexname NOT LIKE '%_pkey'
    """)
    indexes = cursor.fetchall()

    for schema, table, index_name, index_def in indexes:
        ddls[f"index_{index_name}"] = index_def

    # Get sequences
    cursor.execute(f"""
        SELECT sequence_name FROM information_schema.sequences 
        WHERE sequence_schema = '{schema}'
    """)
    sequences = cursor.fetchall()

    for seq_name, in sequences:
        cursor.execute(f"""
            SELECT 
                'CREATE SEQUENCE ' || sequence_name || 
                ' START WITH ' || start_value ||
                ' INCREMENT BY ' || increment ||
                ' MINVALUE ' || minimum_value ||
                ' MAXVALUE ' || maximum_value ||
                CASE WHEN cycle_option = 'YES' THEN ' CYCLE' ELSE ' NO CYCLE' END ||
                ';' as sequence_ddl
            FROM information_schema.sequences 
            WHERE sequence_name = '{seq_name}' AND sequence_schema = '{schema}'
        """)
        complete_ddl = cursor.fetchone()
        ddls[f"sequence_{seq_name}"] = complete_ddl[0] if complete_ddl else f"-- Sequence: {seq_name}"

    connection.close()

    return {
        'source_database': f"PostgreSQL - {database_name or secret.get('database')}",
        'extracted_ddls': ddls,
        'total_objects': len(ddls)
    }

def lambda_handler(event, context):
    """Handle both Bedrock Agent and direct AgentCore invocation requests"""
    # Support both payload formats
    action_group = event.get('actionGroup', '')
    api_path = event.get('apiPath', '')
    http_method = event.get('httpMethod', '')
    
    if api_path == '/analyze-postgresql' and http_method == 'POST':
        # Extract request body - handle both formats
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
        
        database_name = properties.get('database_name') if isinstance(properties, dict) else None
        specific_tables = properties.get('specific_tables', []) if isinstance(properties, dict) else []
        
        if isinstance(specific_tables, str) and '<item>' in specific_tables:
            specific_tables = re.findall(r'<item>(.*?)</item>', specific_tables)
        elif isinstance(specific_tables, str):
            specific_tables = [specific_tables] if specific_tables else []
        
        try:
            result = extract_postgresql_ddl(database_name, specific_tables if specific_tables else None)
            
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': action_group,
                    'apiPath': api_path,
                    'httpMethod': http_method,
                    'httpStatusCode': 200,
                    'responseBody': {
                        'application/json': {
                            'body': json.dumps(result)
                        }
                    }
                }
            }
        except Exception as e:
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': action_group,
                    'apiPath': api_path,
                    'httpMethod': http_method,
                    'httpStatusCode': 500,
                    'responseBody': {
                        'application/json': {
                            'body': json.dumps({'error': str(e)})
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
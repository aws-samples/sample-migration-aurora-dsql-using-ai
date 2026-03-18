#!/usr/bin/env python3
"""
AgentCore Agent Invocation Script
Usage: python3 invoke_agentcore_agent.py "USER_QUERY" "AGENT_NAME" "SESSION_ID"
       python3 invoke_agentcore_agent.py "USER_QUERY" --stack "STACK_NAME" "SESSION_ID"
"""

import sys
import json
import boto3
import uuid
import re
from datetime import datetime

# AgentCore configuration mapping
AGENTCORE_AGENTS = {
    'dsqlanalyzer': {
        'stack_name': 'tst2',  # Analyzer Agentcore stack name
        'region': 'us-east-1'
    },
    'dms': {
        'stack_name': 'dmt',  # DMS AgentCore stack name
        'region': 'us-east-1'
    }
}

def get_agent_runtime_id(agent_name_or_id, region='us-east-1'):
    """
    Get agent runtime ID from configuration or CloudFormation stack
    
    Args:
        agent_name_or_id: Agent name from AGENTCORE_AGENTS or direct runtime ID
        region: AWS region
    
    Returns:
        str: Agent runtime ID
    """
    # Check if it's a configured agent name
    if agent_name_or_id in AGENTCORE_AGENTS:
        config = AGENTCORE_AGENTS[agent_name_or_id]
        stack_name = config['stack_name']
        region = config.get('region', region)
        
        # Get runtime ID from CloudFormation
        cfn = boto3.client('cloudformation', region_name=region)
        try:
            response = cfn.describe_stacks(StackName=stack_name)
            outputs = response['Stacks'][0]['Outputs']
            return next(o['OutputValue'] for o in outputs if o['OutputKey'] == 'AgentRuntimeId'), region
        except Exception as e:
            raise Exception(f"Error getting agent runtime ID from stack {stack_name}: {e}")
    
    # Otherwise assume it's a direct runtime ID
    return agent_name_or_id, region

def clean_xml_tags(content):
    """Remove XML wrapper tags from response"""
    for tag in ['answer', 'answer_part', 'text']:
        content = re.sub(f'<{tag}>', '', content)
        content = re.sub(f'</{tag}>', '', content)
    content = re.sub(r'<sources>.*?</sources>', '', content, flags=re.DOTALL)
    return content.strip()

def format_output(data):
    """Format agent output for display"""
    if data.get('status') != 'success':
        print("\n[ERROR]")
        print(json.dumps(data, indent=2))
        return
    
    result = data.get('result', {}).get('result', {})
    
    print("\n" + "="*80)
    print("AURORA DSQL COMPATIBILITY ANALYSIS")
    print("="*80)
    print(f"\nSession ID: {data.get('sessionId', 'N/A')}")
    print(f"Timestamp: {data.get('timestamp', 'N/A')}")
    
    # Debug: show if response is missing
    if 'response' not in result or not result['response']:
        print("\n[No response received from agent]")
        print("\nFull data structure:")
        print(json.dumps(data, indent=2))
        return
    
    if 'response' in result:
        response_text = clean_xml_tags(result['response'])
        print("\n" + "-"*80)
        print("ANALYSIS:")
        print("-"*80)
        print(response_text)
    
    print("\n" + "="*80 + "\n")

def invoke_agentcore_agent(user_query, session_id, agent_runtime_id, region='us-east-1'):
    """
    Invoke AgentCore agent and return the response
    
    Args:
        user_query: The user's question/query
        session_id: Session ID for conversation continuity
        agent_runtime_id: AgentCore runtime ID (e.g., tst2_dsqlanalyzer-skSdFBG6jM)
        region: AWS region
    
    Returns:
        dict: Response from the agent
    """
    try:
        client = boto3.client('bedrock-agentcore', region_name=region)
        
        # Build the agent runtime ARN
        account_id = boto3.client('sts').get_caller_identity()['Account']
        agent_runtime_arn = f"arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/{agent_runtime_id}"
        
        # Build payload
        payload = json.dumps({"message": user_query})
        
        # Invoke the agent
        response = client.invoke_agent_runtime(
            agentRuntimeArn=agent_runtime_arn,
            runtimeSessionId=session_id,
            payload=payload
        )
        
        # Parse the streaming response body
        response_body = response['response'].read().decode('utf-8')
        
        # Try to parse as JSON
        try:
            result = json.loads(response_body)
        except:
            result = {'response': response_body}
        
        return {
            'status': 'success',
            'result': result,
            'sessionId': session_id,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'sessionId': session_id,
            'timestamp': datetime.now().isoformat()
        }

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 invoke_agentcore_agent.py USER_QUERY AGENT_NAME [SESSION_ID]")
        print("\nConfigured agents:")
        for name, config in AGENTCORE_AGENTS.items():
            print(f"  - {name}: {config['stack_name']} ({config.get('region', 'us-east-1')})")
        print("\nOr use direct runtime ID:")
        print("       python3 invoke_agentcore_agent.py USER_QUERY AGENT_RUNTIME_ID [SESSION_ID]")
        print("\nExamples:")
        print('  python3 invoke_agentcore_agent.py "Analyze techmart_db" dsqlanalyzer')
        print('  python3 invoke_agentcore_agent.py "Analyze techmart_db" "tst2_dsqlanalyzer-ABC123"')
        sys.exit(1)
    
    user_query = sys.argv[1]
    agent_name_or_id = sys.argv[2]
    session_id = sys.argv[3] if len(sys.argv) > 3 else str(uuid.uuid4())
    
    # Get agent runtime ID (from config or direct)
    try:
        agent_runtime_id, region = get_agent_runtime_id(agent_name_or_id)
    except Exception as e:
        print(json.dumps({'status': 'error', 'error': str(e)}))
        sys.exit(1)
    
    # Invoke the agent
    result = invoke_agentcore_agent(user_query, session_id, agent_runtime_id, region)
    
    # Format and print the result
    format_output(result)

if __name__ == "__main__":
    main()
import json
from django.shortcuts import render
from django.http import JsonResponse
from .forms import LoadPDBForm, PyMOLQueryForm
from claude_client import ClaudeClient
import xmlrpc.client
import os
from django.core.cache import cache
from django.conf import settings

cmd = xmlrpc.client.ServerProxy('http://localhost:9123')
# Add this function to get the template path
def get_template_path():
    return "/Users/dylanabramson/Desktop/ClaudePyMOLClient/templates/pymol.jinja"

def pymol_interface(request):
    load_form = LoadPDBForm()
    query_form = PyMOLQueryForm()
    chat_history = cache.get('chat_history', [])
    return render(request, 'claude_app/pymol_interface.html', {
        'load_form': load_form,
        'query_form': query_form,
        'chat_history': chat_history
    })

def load_pdb(request):
    if request.method == 'POST':
        form = LoadPDBForm(request.POST)
        if form.is_valid():
            pdb_id = form.cleaned_data['pdb_id']
            try:
                cmd.do(f"fetch {pdb_id}")
                pdb_dir = os.path.join(settings.BASE_DIR, 'claude_app', 'static', 'pdb_files')
                os.makedirs(pdb_dir, exist_ok=True)
                pdb_filename = f'{pdb_id}.pdb'
                pdb_path = os.path.join(pdb_dir, pdb_filename)
                cmd.do(f"save {pdb_path}")
                
                cache.set('current_pdb_id', pdb_id)
                cache.set('current_pdb_path', pdb_path)
                # Clear previous query history and chat history when loading a new PDB
                cache.set('query_history', [])
                cache.set('chat_history', [])
                return JsonResponse({'success': True, 'message': f'PDB {pdb_id} loaded successfully'})
            except Exception as e:
                return JsonResponse({'success': False, 'message': str(e)})
        print(form.errors, " HERE ARE THE ERRORS")
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def query_claude_and_run_pymol(request):
    if request.method == 'POST':
        form = PyMOLQueryForm(request.POST)
        if form.is_valid():
            client = ClaudeClient(template_file=get_template_path())
            query = form.cleaned_data['query']

            current_pdb_id = cache.get('current_pdb_id', 'Unknown')
            current_pdb_path = cache.get('current_pdb_path', None)
            query_history = cache.get('query_history', [])
            chat_history = cache.get('chat_history', [])

            context = {
                'query': query,
                'query_history': query_history,
            }

            claude_response = client.query(**context)
            try:
                response_data = json.loads(claude_response)

                # Update query history and chat history
                query_history.append({'query': query, 'response': response_data['explanation']})
                chat_history.append({'role': 'user', 'content': query})
                chat_history.append({'role': 'assistant', 'content': response_data['explanation']})

                cache.set('query_history', query_history)
                cache.set('chat_history', chat_history)

                return JsonResponse({
                    'success': True,
                    'claude_response': response_data['explanation'],
                    'commands': response_data['commands'],
                    'chat_history': chat_history
                })
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'message': 'Error parsing JSON response from Claude'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid form data'})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'})

def execute_commands(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        commands = data.get('commands', [])
        all_results = run_commands(commands)

        return JsonResponse({
            'success': True,
            'results': all_results
        })
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'})

def execute_pymol_command(command):
    try:
        cmd.do(command)
        return f"Command: {command}"
    except Exception as e:
        print(e)
        return f"Command: {command}\nError: {str(e)}"

def execute_python_commands(command):
    try:
        exec(command)
        return f"Python Command: {command}"
    except Exception as e:
        print(e)
        return f"Python Command: {command}\nError: {str(e)}"

def run_commands(commands):
    results = []
    for command in commands:
        if command['type'] == 'python':
            results.append(execute_python_command(command['command']))
        elif command['type'] == 'pymol':
            results.append(execute_pymol_command(command['command']))
    return results
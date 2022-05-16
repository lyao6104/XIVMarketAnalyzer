from email import contentmanager
import json

variables_path = ""
variables_store = {}
variables_initialized = False


def init(path):
    global variables_path, variables_store, variables_initialized
    variables_path = path
    try:
        variables_file = open(variables_path, mode="r", encoding="utf-8")
    except FileNotFoundError:
        pass
    else:
        contents = variables_file.read()
        variables_file.close()
        if len(contents) > 0:
            variables_store = json.loads(contents)
    variables_initialized = True


def close():
    global variables_path, variables_store, variables_initialized
    if not variables_initialized:
        raise Exception("Variable store has not been initialized.")
    variables_file = open(variables_path, mode="w", encoding="utf-8")
    variables_file.write(json.dumps(variables_store, sort_keys=True, indent=4))
    variables_file.close()
    variables_initialized = False


def set_variable(key, value):
    global variables_store, variables_initialized
    if not variables_initialized:
        raise Exception("Variable store has not been initialized.")
    variables_store[key] = value


def get_variable(key):
    global variables_store, variables_initialized
    if not variables_initialized:
        raise Exception("Variable store has not been initialized.")
    return variables_store.get(key)

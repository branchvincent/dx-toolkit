import os
from dxpy.nextflow.nextflow_templates import get_nextflow_dxapp
from dxpy.nextflow.nextflow_templates import get_nextflow_src
import tempfile
import dxpy
import json
from distutils.dir_util import copy_tree

def get_template_dir():
    return os.path.join(os.path.dirname(dxpy.__file__), 'templating', 'templates', 'nextflow')


def write_exec(folder, content):
    exec_file = f"{folder}/nextflow.sh"
    os.makedirs(os.path.dirname(os.path.abspath(exec_file)), exist_ok=True)
    with open(exec_file, "w") as exec:
        exec.write(content)


def write_dxapp(folder, content):
    dxapp_file = f"{folder}/dxapp.json"
    with open(dxapp_file, "w") as dxapp:
        json.dump(content, dxapp)


def build_pipeline_from_repository(repository, tag, profile, brief):
    """
    :param repository: URL to git repository
    :type repository: string
    :param tag: tag of given git repository. if not given, default branch is used.
    :type tag: string
    :param profile: Custom NF profile, for more information visit https://www.nextflow.io/docs/latest/config.html#config-profiles
    :type profile: string
    :param brief: Level of verbosity
    :type brief: boolean

    Runs the Nextflow Pipeline Importer app, which creates NF applet from given repository.
    """
    build_project_id = dxpy.WORKSPACE_ID
    if build_project_id is None:
        parser.error(
            "Can't create an applet without specifying a destination project; please use the -d/--destination flag to explicitly specify a project")
    input_hash = {
        "repository_url": repository,
        "repository_tag": tag,
        "config_profile": profile
    }

    api_options = {
        "name": "Nextflow build of %s" % (repository),
        "input": input_hash,
        "project": build_project_id,
    }

    # TODO: this will have to be an app app_run!
    app_run_result = dxpy.api.applet_run('applet-GFb8kQj0469zQ5P5BQGYpKJz', input_params=api_options)
    job_id = app_run_result["id"]
    if not brief:
        print("Started builder job %s" % (job_id,))
    dxpy.DXJob(job_id).wait_on_done(interval=1)
    applet_id, _ = dxpy.get_dxlink_ids(dxpy.api.job_describe(job_id)['output']['output_applet'])
    if not brief:
        print("Created Nextflow pipeline %s" % (applet_id))
    else:
        print(applet_id)
    return applet_id

def prepare_nextflow(resources_dir, profile):
    """
    :param resources_dir: Directory with all resources needed for Nextflow Pipeline. Usually directory with user's NF files.
    :type resources_dir: str or Path
    :param profile: Custom NF profile, for more information visit https://www.nextflow.io/docs/latest/config.html#config-profiles
    :type profile: string

    Creates files for creating applet, such as dxapp.json and source file. These files are created in temp directory.
    """
    assert os.path.exists(resources_dir)
    inputs = []
    # dxapp_dir = tempfile.mkdtemp(prefix="dx.nextflow.")
    os.makedirs(".dx.nextflow", exist_ok=True)
    dxapp_dir = os.path.join(resources_dir, '.dx.nextflow')
    if os.path.exists(f"{resources_dir}/nextflow_schema.json"):
        inputs = prepare_inputs(f"{resources_dir}/nextflow_schema.json")
    DXAPP_CONTENT = get_nextflow_dxapp(inputs)
    EXEC_CONTENT = get_nextflow_src(inputs, profile)
    copy_tree(get_template_dir(), dxapp_dir)
    print(resources_dir)
    print(os.path.join(dxapp_dir, 'resources', 'home', 'dnanexus', 'NF'))
    write_dxapp(dxapp_dir, DXAPP_CONTENT)
    write_exec(dxapp_dir, EXEC_CONTENT)
    import glob
    for filename in glob.iglob(dxapp_dir + '**/**', recursive=True):
        print(filename)

    return dxapp_dir

# TODO: Add docstrings for all the methods.
def prepare_inputs(schema_file):
    def get_default_input_value(key):
        types = {
            "hidden": "false",
            "help": "Default help message"
            # TODO: add directory + file + path
        }
        if key in types:
            return types[key]
        return "NOT_IMPLEMENTED"

    def get_dx_type(nf_type):
        types = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "boolean",
            "object": "hash"  # TODO: check default values
            # TODO: add directory + file + path
        }
        if nf_type in types:
            return types[nf_type]
        return "string"
        # raise Exception(f"type {nf_type} is not supported by DNAnexus")

    inputs = []
    try:
        with open(schema_file, "r") as fh:
            schema = json.load(fh)
    except Exception as json_e:
        raise AssertionError(json_e)
    for d_key, d_schema in schema.get("definitions", {}).items():
        required_inputs = d_schema.get("required", [])
        for property_key, property in d_schema.get("properties", {}).items():
            dx_input = {}
            dx_input["name"] = f"{property_key}"
            dx_input["title"] = f"{property.get(property_key, dx_input['name'])}"
            dx_input["help"] = f"{property.get(property_key, get_default_input_value('help'))}"
            if property_key in property:
                dx_input["default"] = f"{property.get(property_key)}"
            dx_input["hidden"] = f"{property.get(property_key, get_default_input_value('hidden'))}"
            dx_input["class"] = f"{get_dx_type(property_key)}"
            if property_key not in required_inputs:
                dx_input["optional"] = True
            inputs.append(dx_input)
    return inputs

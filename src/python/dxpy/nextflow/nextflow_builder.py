#!/usr/bin/env python

import os
import dxpy
import json
import argparse
from glob import glob
import tempfile

from dxpy.nextflow.nextflow_templates import (get_nextflow_dxapp, get_nextflow_src)
from dxpy.nextflow.nextflow_utils import (get_template_dir, write_exec, write_dxapp, get_importer_name)
from dxpy.cli.exec_io import parse_obj
from distutils.dir_util import copy_tree
parser = argparse.ArgumentParser(description="Uploads a DNAnexus App.")


def build_pipeline_from_repository(repository, tag, profile="", github_creds=None, brief=False):
    """
    :param repository: URL to a Git repository
    :type repository: string
    :param tag: tag of a given Git repository. If it is not provided, the default branch is used.
    :type tag: string
    :param profile: Custom Nextflow profile, for more information visit https://www.nextflow.io/docs/latest/config.html#config-profiles
    :type profile: string
    :param brief: Level of verbosity
    :type brief: boolean
    :returns: ID of the created applet

    Runs the Nextflow Pipeline Importer app, which creates a Nextflow applet from a given Git repository.
    """

    build_project_id = dxpy.WORKSPACE_ID
    if build_project_id is None:
        parser.error(
            "Can't create an applet without specifying a destination project; please use the -d/--destination flag to explicitly specify a project")

    input_hash = {
        "repository_url": repository,
    }
    if tag:
        input_hash["repository_tag"] = tag
    if profile:
        input_hash["config_profile"] = profile
    if github_creds:
        input_hash["github_credentials"] = parse_obj(github_creds, "file")

    nf_builder_job = dxpy.DXApp(name=get_importer_name()).run(app_input=input_hash, project=build_project_id, name="Nextflow build of %s" % (repository), detach=True)

    if not brief:
        print("Started builder job %s" % (nf_builder_job.get_id(),))
    nf_builder_job.wait_on_done(interval=1)
    applet_id, _ = dxpy.get_dxlink_ids(nf_builder_job.describe(fields={"output": True})['output']['output_applet'])
    if not brief:
        print("Created Nextflow pipeline %s" % (applet_id))
    else:
        print(applet_id)
    return applet_id

def prepare_nextflow(resources_dir, profile):
    """
    :param resources_dir: Directory with all resources needed for the Nextflow pipeline. Usually directory with user's Nextflow files.
    :type resources_dir: str or Path
    :param profile: Custom Nextflow profile. More profiles can be provided by using comma separated string (without whitespaces).
    :type profile: string
    :returns: Path to the created dxapp_dir
    :rtype: Path

    Creates files necessary for creating an applet on the Platform, such as dxapp.json and a source file. These files are created in '.dx.nextflow' directory.
    """
    assert os.path.exists(resources_dir)
    if not glob(os.path.join(resources_dir, "*.nf")):
        raise dxpy.app_builder.AppBuilderException("Directory %s does not contain Nextflow file (*.nf): not a valid Nextflow directory" % resources_dir)
    inputs = []
    dxapp_dir = tempfile.mkdtemp(prefix=".dx.nextflow")
    if os.path.exists("{}/nextflow_schema.json".format(resources_dir)):
        inputs = prepare_inputs("{}/nextflow_schema.json".format(resources_dir))
    dxapp_content = get_nextflow_dxapp(inputs, os.path.basename(resources_dir))
    exec_content = get_nextflow_src(inputs=inputs, profile=profile)
    copy_tree(get_template_dir(), dxapp_dir)
    write_dxapp(dxapp_dir, dxapp_content)
    write_exec(dxapp_dir, exec_content)
    return dxapp_dir


def prepare_inputs(schema_file):
    """
    :param schema_file: path to nextflow_schema.json file
    :type schema_file: str or Path
    :returns: DNAnexus datatype used in dxapp.json inputSpec field
    :rtype: string
    Creates DNAnexus inputs (inputSpec) from Nextflow inputs.
    """

    def get_dx_type(nf_type, nf_format=None):
        types = {
            "string": "string",
            "integer": "int",
            "number": "float",
            "boolean": "boolean",
            "object": "hash"
        }
        str_types = {
            "file-path": "file",
            "directory-path": "string",  # So far we will stick with strings dx://...
            "path": "string"
        }
        if nf_type == "string" and nf_format in str_types:
            return str_types[nf_format]
        elif nf_type in types:
            return types[nf_type]
        raise Exception("type {} is not supported by DNAnexus".format(nf_type))

    inputs = []
    with open(schema_file, "r") as fh:
        schema = json.load(fh)
    for d_key, d_schema in schema.get("definitions", {}).items():
        required_inputs = d_schema.get("required", [])
        for property_key, property in d_schema.get("properties", {}).items():
            dx_input = {}
            dx_input["name"] = property_key
            dx_input["title"] = dx_input['name']
            if "help_text" in property:
                dx_input["help"] = property.get('help_text')
            if "default" in property:
                dx_input["default"] = property.get("default")
            dx_input["hidden"] = property.get('hidden', False)
            dx_input["class"] = get_dx_type(property.get("type"), property.get("format"))
            if property_key not in required_inputs:
                dx_input["optional"] = True
                if dx_input.get("help") is not None:
                    dx_input["help"] = "(Optional) {}".format(dx_input["help"])
            inputs.append(dx_input)
    return inputs
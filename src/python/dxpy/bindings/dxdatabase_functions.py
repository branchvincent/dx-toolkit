# Copyright (C) 2013-2016 DNAnexus, Inc.
#
# This file is part of dx-toolkit (DNAnexus platform client libraries).
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may not
#   use this file except in compliance with the License. You may obtain a copy
#   of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

'''
Helper Functions
****************

The following helper functions are useful shortcuts for interacting with Database objects.

'''

from __future__ import print_function, unicode_literals, division, absolute_import

import os, sys, math, mmap, stat
import hashlib
import traceback
import warnings
from collections import defaultdict
import multiprocessing

import dxpy
from .. import logger
from . import dxfile, DXFile
from . import dxdatabase, DXDatabase
from .dxfile import FILE_REQUEST_TIMEOUT
from ..compat import open, USING_PYTHON2
from ..exceptions import DXFileError, DXPartLengthMismatchError, DXChecksumMismatchError, DXIncompleteReadsError, err_exit
from ..utils import response_iterator
import subprocess

def download_dxdatabasefile(dxid, filename, src_filename, file_status, chunksize=dxfile.DEFAULT_BUFFER_SIZE, append=False, show_progress=False,
                    project=None, describe_output=None, **kwargs):
    '''
    :param dxid: DNAnexus file ID or DXFile (file handler) object
    :type dxid: string or DXFile
    :param filename: Local filename
    :type filename: string
    :param src_filename: Name of database file or folder being downloaded
    :type src_filename: string
    :param file_status: Metadata for the source file being downloaded
    :type file_status: dict
    :param append: If True, appends to the local file (default is to truncate local file if it exists)
    :type append: boolean
    :param project: project to use as context for this download (may affect
            which billing account is billed for this download). If None or
            DXFile.NO_PROJECT_HINT, no project hint is supplied to the API server.
    :type project: str or None
    :param describe_output: (experimental) output of the file-xxxx/describe API call,
            if available. It will make it possible to skip another describe API call.
            It should contain the default fields of the describe API call output and
            the "parts" field, not included in the output by default.
    :type describe_output: dict or None

    Downloads the remote file referenced by *src_filename* from database referenced
    by *dxid* and saves it to *filename*.

    Example::

        download_dxdatabasefile("database-xxxx", "localfilename", "tablename/data.parquet)

    '''
    # retry the inner loop while there are retriable errors

    part_retry_counter = defaultdict(lambda: 3)
    success = False
    while not success:
        success = _download_dxdatabasefile(dxid,
                                   filename,
                                   src_filename,
                                   file_status,
                                   part_retry_counter,
                                   chunksize=chunksize,
                                   append=append,
                                   show_progress=show_progress,
                                   project=project,
                                   describe_output=describe_output,
                                   **kwargs)


# Check if a program (wget, curl, etc.) is on the path, and
# can be called.
def _which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    for path in os.environ["PATH"].split(os.pathsep):
        exe_file = os.path.join(path, program)
        if is_exe(exe_file):
            return exe_file
    return None

# Caluclate the md5 checkum for [filename], and raise
# an exception if the checksum is wrong.
def _verify(filename, md5digest):
    md5sum_exe = _which("md5sum")
    if md5sum_exe is None:
        err_exit("md5sum is not installed on this system")
    cmd = [md5sum_exe, "-b", filename]
    try:
        print("Calculating checksum")
        cmd_out = subprocess.check_output(cmd)
    except subprocess.CalledProcessError:
        err_exit("Failed to run md5sum: " + str(cmd))

    line = cmd_out.strip().split()
    if len(line) != 2:
        err_exit("md5sum returned weird results: " + str(line))
    actual_md5 = line[0]
    md5digest = md5digest.encode("ascii")

    # python-3 : both digests have to be in bytes
    if actual_md5 != md5digest:
        err_exit("Checksum doesn't match " + str(actual_md5) + "  expected:" + str(md5digest))
    print("Checksum correct")

def do_debug(msg):
    print("(debug) " + msg)

def _download_dxdatabasefile(dxid, filename, src_filename, file_status, part_retry_counter,
                     chunksize=dxfile.DEFAULT_BUFFER_SIZE, append=False, show_progress=False,
                     project=None, describe_output=None, **kwargs):
    '''
    Core of download logic. Download file-id *dxid* and store it in
    a local file *filename*.

    The return value is as follows:
    - True means the download was successfully completed
    - False means the download was stopped because of a retryable error
    - Exception raised for other errors
    '''
    def print_progress(bytes_downloaded, file_size, action="Downloaded"):
        num_ticks = 60

        effective_file_size = file_size or 1
        if bytes_downloaded > effective_file_size:
            effective_file_size = bytes_downloaded

        ticks = int(round((bytes_downloaded / float(effective_file_size)) * num_ticks))
        percent = int(math.floor((bytes_downloaded / float(effective_file_size)) * 100))

        fmt = "[{done}{pending}] {action} {done_bytes:,}{remaining} bytes ({percent}%) {name}"
        # Erase the line and return the cursor to the start of the line.
        # The following VT100 escape sequence will erase the current line.
        sys.stderr.write("\33[2K")
        sys.stderr.write(fmt.format(action=action,
                                    done=("=" * (ticks - 1) + ">") if ticks > 0 else "",
                                    pending=" " * (num_ticks - ticks),
                                    done_bytes=bytes_downloaded,
                                    remaining=" of {size:,}".format(size=file_size) if file_size else "",
                                    percent=percent,
                                    name=filename))
        sys.stderr.flush()
        sys.stderr.write("\r")
        sys.stderr.flush()

    do_debug("dxdatabase_functions.py _download_dxdatabasefile - filename {}".format(filename)) 

    _bytes = 0

    if isinstance(dxid, DXDatabase):
        do_debug("dxdatabase_functions.py _download_dxdatabasefile - already a database - id = {}".format(dxid)) 
        dxdatabase = dxid
    else:
        do_debug("dxdatabase_functions.py _download_dxdatabasefile - created database handler - id = {}".format(dxid)) 
        dxdatabase = DXDatabase(dxid, mode="r", project=(project if project != DXFile.NO_PROJECT_HINT else None))

    do_debug("dxdatabase_functions.py _download_dxdatabasefile - dxfile is a dxdatabase: {}".format(dxdatabase)) 

    if describe_output and describe_output.get("parts") is not None:
        dxdatabase_desc = describe_output
    else:
        dxdatabase_desc = dxdatabase.describe(fields={"parts"}, default_fields=True, **kwargs)

    do_debug("dxdatabase_functions.py _download_dxdatabasefile - dxdatabase_desc {}".format(dxdatabase_desc)) 

    # TODO: clean up usage of 'parts'
    # TODO: don't need md5.
    parts = {u'1': {u'state': u'complete', u'md5': u'85c149c110a91df15ffd6a2c9da45cdb', u'size': file_status["size"]}}
    parts_to_get = sorted(parts, key=int)
    file_size = file_status["size"]

    do_debug("dxdatabase_functions.py _download_dxdatabasefile - parts = {}".format(parts)) 
    do_debug("dxdatabase_functions.py _download_dxdatabasefile - file_size {}".format(file_size)) 

    offset = 0
    for part_id in parts_to_get:
        parts[part_id]["start"] = offset
        offset += parts[part_id]["size"]

    do_debug("dxdatabase_functions.py _download_dxdatabasefile - filename = {}, src_filename = {}".format(filename, src_filename)) 
    
    # Create proper destination path, including any subdirectories needed within path.
    ensure_local_dir(filename);
    dest_path = os.path.join(filename, src_filename)
    dest_dir_idx = dest_path.rfind("/");
    if dest_dir_idx != -1:
        dest_dir = dest_path[:dest_dir_idx]
        ensure_local_dir(dest_dir)      

    # Use dest_path not filename
    if append:
        fh = open(dest_path, "ab")
    else:
        try:
            fh = open(dest_path, "rb+")
        except IOError:
            fh = open(dest_path, "wb")

    if show_progress:
        print_progress(0, None)

    def get_chunk(part_id_to_get, start, end):
        do_debug("dxdatabase_functions.py get_chunk - start {}, end {}, part id {}".format(start, end, part_id_to_get))
        url, headers = dxdatabase.get_download_url(src_filename=src_filename, project=project, **kwargs)
        do_debug("dxdatabase_functions.py get_chunk - url = {}".format(url))
 
        # If we're fetching the whole object in one shot, avoid setting the Range header to take advantage of gzip
        # transfer compression
        sub_range = False
        if len(parts) > 1 or (start > 0) or (end - start + 1 < parts[part_id_to_get]["size"]):
            sub_range = True
        # TODO: read the whole range here since it's a URL
        data_url = dxpy._dxhttp_read_range(url, headers, start, end, FILE_REQUEST_TIMEOUT, sub_range)
        do_debug("dxdatabase_functions.py get_chunk - data_url = {}".format(data_url))
        # 'data_url' is the s3 URL, so read again, just like in DNAxFileSystem
        data = dxpy._dxhttp_read_range(data_url, headers, start, end, FILE_REQUEST_TIMEOUT, sub_range)
        return part_id_to_get, data

    def chunk_requests():
        for part_id_to_chunk in parts_to_get:
            part_info = parts[part_id_to_chunk]
            for chunk_start in range(part_info["start"], part_info["start"] + part_info["size"], chunksize):
                chunk_end = min(chunk_start + chunksize, part_info["start"] + part_info["size"]) - 1
                yield get_chunk, [part_id_to_chunk, chunk_start, chunk_end], {}

    def verify_part(_part_id, got_bytes, hasher):
        if got_bytes is not None and got_bytes != parts[_part_id]["size"]:
            msg = "Unexpected part data size in {} part {} (expected {}, got {})"
            msg = msg.format(dxdatabase.get_id(), _part_id, parts[_part_id]["size"], got_bytes)
            raise DXPartLengthMismatchError(msg)
        if hasher is not None and "md5" not in parts[_part_id]:
            warnings.warn("Download of file {} is not being checked for integrity".format(dxdatabase.get_id()))
        elif hasher is not None and hasher.hexdigest() != parts[_part_id]["md5"]:
            msg = "Checksum mismatch in {} part {} (expected {}, got {})"
            msg = msg.format(dxdatabase.get_id(), _part_id, parts[_part_id]["md5"], hasher.hexdigest())
            raise DXChecksumMismatchError(msg)

    with fh:
        last_verified_pos = 0

        if fh.mode == "rb+":
            # We already downloaded the beginning of the file, verify that the
            # chunk checksums match the metadata.
            last_verified_part, max_verify_chunk_size = None, 1024*1024
            try:
                for part_id in parts_to_get:
                    part_info = parts[part_id]

                    # if "md5" not in part_info:
                    #     raise DXFileError("File {} does not contain part md5 checksums".format(dxdatabase.get_id()))
                    bytes_to_read = part_info["size"]
                    hasher = hashlib.md5()
                    while bytes_to_read > 0:
                        chunk = fh.read(min(max_verify_chunk_size, bytes_to_read))
                        if len(chunk) < min(max_verify_chunk_size, bytes_to_read):
                            raise DXFileError("Local data for part {} is truncated".format(part_id))
                        hasher.update(chunk)
                        bytes_to_read -= max_verify_chunk_size
                    if hasher.hexdigest() != part_info["md5"]:
                        raise DXFileError("Checksum mismatch when verifying downloaded part {}".format(part_id))
                    else:
                        last_verified_part = part_id
                        last_verified_pos = fh.tell()
                        if show_progress:
                            _bytes += part_info["size"]
                            print_progress(_bytes, file_size, action="Verified")
            except (IOError, DXFileError) as e:
                logger.debug(e)
            fh.seek(last_verified_pos)
            fh.truncate()
            if last_verified_part is not None:
                del parts_to_get[:parts_to_get.index(last_verified_part)+1]
            if show_progress and len(parts_to_get) < len(parts):
                print_progress(last_verified_pos, file_size, action="Resuming at")
            logger.debug("Verified %s/%d downloaded parts", last_verified_part, len(parts_to_get))

        try:
            # Main loop. In parallel: download chunks, verify them, and write them to disk.
            get_first_chunk_sequentially = (file_size > 128 * 1024 and last_verified_pos == 0 and dxpy.JOB_ID)
            cur_part, got_bytes, hasher = None, None, None
            for chunk_part, chunk_data in response_iterator(chunk_requests(),
                                                            dxdatabase._http_threadpool,
                                                            do_first_task_sequentially=get_first_chunk_sequentially):
                if chunk_part != cur_part:
                    # TODO: remove permanently if we don't find use for this
                    # verify_part(cur_part, got_bytes, hasher)
                    cur_part, got_bytes, hasher = chunk_part, 0, hashlib.md5()
                got_bytes += len(chunk_data)
                hasher.update(chunk_data)
                fh.write(chunk_data)
                if show_progress:
                    _bytes += len(chunk_data)
                    print_progress(_bytes, file_size)
            # TODO: same as above
            # verify_part(cur_part, got_bytes, hasher)
            if show_progress:
                print_progress(_bytes, file_size, action="Completed")
        except DXFileError:
            print(traceback.format_exc(), file=sys.stderr)
            part_retry_counter[cur_part] -= 1
            if part_retry_counter[cur_part] > 0:
                print("Retrying {} ({} tries remain for part {})".format(dxdatabase.get_id(), part_retry_counter[cur_part], cur_part),
                      file=sys.stderr)
                return False
            raise

        if show_progress:
            sys.stderr.write("\n")

        return True


def list_subfolders(project, path, recurse=True):
    '''
    :param project: Project ID to use as context for the listing
    :type project: string
    :param path: Subtree root path
    :type path: string
    :param recurse: Return a complete subfolders tree
    :type recurse: boolean

    Returns a list of subfolders for the remote *path* (included to the result) of the *project*.

    Example::

        list_subfolders("project-xxxx", folder="/input")

    '''
    project_folders = dxpy.get_handler(project).describe(input_params={'folders': True})['folders']
    # TODO: support shell-style path globbing (i.e. /a*/c matches /ab/c but not /a/b/c)
    # return pathmatch.filter(project_folders, os.path.join(path, '*'))
    if recurse:
        return (f for f in project_folders if f.startswith(path))
    else:
        return (f for f in project_folders if f.startswith(path) and '/' not in f[len(path)+1:])

def ensure_local_dir(d):
    do_debug("dxdatabase_functions.py ensure_local_dir - d = {}".format(d)) 
    if not os.path.isdir(d):
        if os.path.exists(d):
            raise DXFileError("Destination location '{}' already exists and is not a directory".format(d))
        logger.debug("Creating destination directory: '%s'", d)
        os.makedirs(d)

# TODO: purge if not needed
def download_folder(project, destdir, folder="/", overwrite=False, chunksize=dxfile.DEFAULT_BUFFER_SIZE,
                    show_progress=False, **kwargs):
    '''
    :param project: Project ID to use as context for this download.
    :type project: string
    :param destdir: Local destination location
    :type destdir: string
    :param folder: Path to the remote folder to download
    :type folder: string
    :param overwrite: Overwrite existing files
    :type overwrite: boolean

    Downloads the contents of the remote *folder* of the *project* into the local directory specified by *destdir*.

    Example::

        download_folder("project-xxxx", "/home/jsmith/input", folder="/input")

    '''

    def compose_local_dir(d, remote_folder, remote_subfolder):
        suffix = remote_subfolder[1:] if remote_folder == "/" else remote_subfolder[len(remote_folder) + 1:]
        if os.sep != '/':
            suffix = suffix.replace('/', os.sep)
        return os.path.join(d, suffix) if suffix != "" else d

    normalized_folder = folder.strip()
    if normalized_folder != "/" and normalized_folder.endswith("/"):
        normalized_folder = normalized_folder[:-1]
    if normalized_folder == "":
        raise DXFileError("Invalid remote folder name: '{}'".format(folder))
    normalized_dest_dir = os.path.normpath(destdir).strip()
    if normalized_dest_dir == "":
        raise DXFileError("Invalid destination directory name: '{}'".format(destdir))
    # Creating target directory tree
    remote_folders = list(list_subfolders(project, normalized_folder, recurse=True))
    if len(remote_folders) <= 0:
        raise DXFileError("Remote folder '{}' not found".format(normalized_folder))
    remote_folders.sort()
    for remote_subfolder in remote_folders:
        ensure_local_dir(compose_local_dir(normalized_dest_dir, normalized_folder, remote_subfolder))

    # Downloading files
    describe_input = dict(fields=dict(folder=True,
                                      name=True,
                                      id=True,
                                      parts=True,
                                      size=True,
                                      drive=True,
                                      md5=True))

    # A generator that returns the files one by one. We don't want to materialize it, because
    # there could be many files here.
    files_gen = dxpy.search.find_data_objects(classname='file', state='closed', project=project,
                                              folder=normalized_folder, recurse=True, describe=describe_input)
    if files_gen is None:
        # In python 3, the generator can be None, and iterating on it
        # will cause an error.
        return

    # Now it is safe, in both python 2 and 3, to iterate on the generator
    for remote_file in files_gen:
        local_filename = os.path.join(compose_local_dir(normalized_dest_dir,
                                                        normalized_folder,
                                                        remote_file['describe']['folder']),
                                      remote_file['describe']['name'])
        if os.path.exists(local_filename) and not overwrite:
            raise DXFileError(
                "Destination file '{}' already exists but no overwrite option is provided".format(local_filename)
            )
        logger.debug("Downloading '%s/%s' remote file to '%s' location",
                     ("" if remote_file['describe']['folder'] == "/" else remote_file['describe']['folder']),
                     remote_file['describe']['name'],
                     local_filename)
        download_dxdatabasefile(remote_file['describe']['id'],
                        local_filename,
                        chunksize=chunksize,
                        project=project,
                        show_progress=show_progress,
                        describe_output=remote_file['describe'],
                        **kwargs)
import csv
import datetime
import glob
import json
import logging
import os
import re
import shutil
import subprocess
import uuid

from typing import Iterator, Optional

import auto_ncov.metadata as metadata


def find_fastq_dirs(config, check_symlinks_complete=True) -> Iterator[Optional[dict[str, object]]]:
    """
    Iterate over contents of `fastq_by_run_dir` from config. Identify directories that
    match the illumina run ID format. If `check_symlinks_complete` is True, then check
    that a `symlinks_complete.json` file exists in the directory. Also consult the list
    of excluded runs, and exclude any directory whose name appears on that list.

    :param config: Application config. Required keys: `["fastq_by_run_dir", "excluded_runs"]`. Optional keys: `["analyze_runs_in_reverse_order"]`
    :type config: dict[str, object]
    :return: A run directory to analyze, or None. If not None, keys are: `["run_id", "fastq_directory", "analysis_parameters"]`
    :rtype: Iterator[Optional[dict[str, object]]]
    """
    miseq_run_id_regex = "\\d{6}_M\\d{5}_\\d+_\\d{9}-[A-Z0-9]{5}"
    nextseq_run_id_regex = "\\d{6}_VH\\d{5}_\\d+_[A-Z0-9]{9}"

    fastq_by_run_dir = config['fastq_by_run_dir']
    subdirs = os.scandir(fastq_by_run_dir)
    if 'analyze_runs_in_reverse_order' in config and config['analyze_runs_in_reverse_order']:
        subdirs = sorted(subdirs, key=lambda x: os.path.basename(x.path), reverse=True)
    for subdir in subdirs:
        run_id = subdir.name
        run_fastq_directory = os.path.abspath(subdir.path)

        matches_miseq_regex = re.match(miseq_run_id_regex, run_id)
        matches_nextseq_regex = re.match(nextseq_run_id_regex, run_id)

        if check_symlinks_complete:
            ready_to_analyze = os.path.exists(os.path.join(subdir.path, "symlinks_complete.json"))
        else:
            ready_to_analyze = True

        not_excluded = run_id not in config['excluded_runs']

        conditions_checked = {
            "is_directory": subdir.is_dir(),
            "matches_illumina_run_id_format": ((matches_miseq_regex is not None) or (matches_nextseq_regex is not None)),
            "ready_to_analyze": ready_to_analyze,
            "not_excluded": not_excluded,
        }

        conditions_met = list(conditions_checked.values())
        
        analysis_parameters = {}
        if all(conditions_met):
            logging.info(json.dumps({"event_type": "fastq_directory_found", "sequencing_run_id": run_id, "fastq_directory_path": os.path.abspath(subdir.path)}))
            analysis_parameters['directory'] = run_fastq_directory
            analysis_parameters['prefix'] = os.path.basename(run_fastq_directory)
            run = {
                "run_id": run_id,
                "fastq_directory": run_fastq_directory,
                "analysis_parameters": analysis_parameters
            }
            yield run
        else:
            logging.debug(json.dumps({"event_type": "directory_skipped", "fastq_directory": run_fastq_directory, "conditions_checked": conditions_checked}))
            yield None
    

def scan(config: dict[str, object]) -> Iterator[Optional[dict[str, object]]]:
    """
    Scanning involves looking for all existing runs, and passing them along to be analyzed.

    :param config: Application config.
    :type config: dict[str, object]
    :return: A run directory to analyze, or None. If not None, keys are: `["run_id", "fastq_directory", "analysis_parameters"]`
    :rtype: Iterator[Optional[dict[str, object]]]
    """
    logging.info(json.dumps({"event_type": "scan_start"}))
    for fastq_dir in find_fastq_dirs(config):    
        yield fastq_dir


def check_analysis_dependencies_complete(pipeline: dict[str, object], analysis: dict[str, object], analysis_run_output_dir: str) -> bool:
    """
    Check that all of the entries in the pipeline's `dependencies` config have completed. If so, return True. Return False otherwise.

    Pipeline completion is determined by the presence of an `analysis_complete.json` file in the analysis output directory.

    :param pipeline:
    :type pipeline: dict[str, object]
    :param analysis:
    :type analysis: dictp[str, object]
    :param analysis_run_output_dir:
    :type analysis_run_output_dir: str
    :return: Whether or not all of the pipelines listed in `dependencies` have completed.
    :rtype: bool
    """
    all_dependencies_complete = False
    if 'dependencies' not in pipeline:
        return True

    dependencies = pipeline['dependencies']
    if dependencies is None:
        return True

    dependencies_complete = []
    dependency_infos = []
    for dependency in dependencies:
        dependency_pipeline_short_name = dependency['pipeline_name'].split('/')[1]
        dependency_pipeline_minor_version = ''.join(dependency['pipeline_version'].rsplit('.', 1)[0])
        dependency_analysis_output_dir_name = '-'.join([dependency_pipeline_short_name, dependency_pipeline_minor_version, 'output'])
        dependency_analysis_complete_path = os.path.join(analysis_run_output_dir, dependency_analysis_output_dir_name, 'analysis_complete.json')
        dependency_analysis_complete = os.path.exists(dependency_analysis_complete_path)
        dependency_info = {
            'pipeline_name': dependency['pipeline_name'],
            'pipeline_version': dependency['pipeline_version'],
            'analysis_complete_path': dependency_analysis_complete_path,
            'analysis_complete': dependency_analysis_complete
        }
        dependency_infos.append(dependency_info)
    dependencies_complete = [dep['analysis_complete'] for dep in dependency_infos]
    logging.info(json.dumps({"event_type": "checked_analysis_dependencies", "all_analysis_dependencies_complete": all(dependencies_complete), "analysis_dependencies": dependency_infos}))
    if all(dependencies_complete):
        all_dependencies_complete = True

    return all_dependencies_complete


def analyze_run(config: dict[str, object], run: dict[str, object]) -> None:
    """
    Initiate an analysis on one directory of fastq files. We assume that the directory of fastq files is named using
    a sequencing run ID.

    Runs the pipeline as defined in the config, with parameters configured for the run to be analyzed. Skips any
    analyses that have already been initiated (whether completed or not).

    Some pipelines may specify that they depend on the outputs of another through their 'dependencies' config.
    For those pipelines, we confirm that all of the upstream analyses that we depend on are complete, or the analysis will be skipped.

    :param config: Application config. Required keys: `["analysis_output_dir", "analysis_work_dir", "pipelines"]`. Optional keys: `["send_notification_emails", "notification_email_addresses"]`
    :type config: dict[str, object]
    :param run: Sequencing run to analyze. Required keys: `["run_id", "fastq_directory", "analysis_parameters"]`
    :type run: dict[str, object]
    :return: None
    :rtype: NoneType
    """
    base_analysis_outdir = config['analysis_output_dir']
    base_analysis_work_dir = config['analysis_work_dir']
    run_id = run['run_id']
    if 'notification_email_addresses' in config:
        notification_email_addresses = config['notification_email_addresses']
    else:
        notification_email_addresses = []

    for pipeline in config['pipelines']:
        pipeline_parameters = pipeline['pipeline_parameters']
        pipeline_short_name = pipeline['pipeline_name'].split('/')[1]
        pipeline_minor_version = ''.join(pipeline['pipeline_version'].rsplit('.', 1)[0])

        analysis_output_dir_name = '-'.join([pipeline_short_name, pipeline_minor_version, 'output'])
        analysis_run_output_dir = os.path.join(str(config['analysis_output_dir']), str(run_id))
        # Pipeline-specific logic
        if pipeline['pipeline_name'] == 'BCCDC-PHL/ncov2019-artic-nf':
            analysis_pipeline_output_dir = os.path.abspath(os.path.join(analysis_run_output_dir, analysis_output_dir_name))
            fastq_dir = run['fastq_directory']
            run_id = run['run_id']
            for pipeline_parameter in pipeline_parameters:
                if pipeline_parameter["flag"] == "--directory":
                    pipeline_parameter["value"] = fastq_dir
                elif pipeline_parameter["flag"] == "--prefix":
                    pipeline_parameter["value"] = run_id

        elif pipeline['pipeline_name'] == 'BCCDC-PHL/ncov-tools-nf':
            # We don't include the '-nf' in the ncov-tools output dir
            analysis_output_dir_name = '-'.join([pipeline_short_name.removesuffix('-nf'), pipeline_minor_version, 'output'])
            artic_minor_version = ""
            for dependency in pipeline['dependencies']:
                if dependency['pipeline_name'] == 'BCCDC-PHL/ncov2019-artic-nf':
                    artic_version = dependency['pipeline_version']
                    artic_minor_version = '.'.join(artic_version.lstrip('v').split('.')[0:2])
            ncov2019_artic_nf_output_dir = "ncov2019-artic-nf-v" + artic_minor_version + "-output"
            analysis_pipeline_output_dir = os.path.abspath(os.path.join(analysis_run_output_dir, ncov2019_artic_nf_output_dir, analysis_output_dir_name))
            analysis_pipeline_input_dir = os.path.abspath(os.path.join(analysis_run_output_dir, ncov2019_artic_nf_output_dir))
            analysis_run_metadata_path = os.path.join(analysis_run_output_dir, 'metadata.tsv')

            # Need to do a separate pass over parameters specifically to
            # remove the metadata flag, to avoid mutating the list of
            # parameters while iterating over it.
            if not os.path.exists(analysis_run_metadata_path):
                run_metadata = metadata.collect_run_metadata(config, run_id)
                if len(run_metadata) > 0:
                    try:
                        with open(analysis_run_metadata_path, 'w') as f:
                            output_fieldnames = ['sample', 'ct', 'date']
                            writer = csv.DictWriter(f, fieldnames=['sample', 'ct', 'date'], dialect='excel-tab')
                            writer.writeheader()
                            for row in run_metadata:
                                for field in output_fieldnames[1:]:
                                    if row[field] is None:
                                        row[field] = "NA"
                                writer.writerow(row)
                        logging.info(json.dumps({"event_type": "wrote_metadata_file", "run_id": run_id, "metadata_file": os.path.abspath(analysis_run_metadata_path)}))
                    except Exception as e: # TODO: Narrow the type of exceptions we catch here
                        # If we can't write a metadata file for the run then
                        # we should exclude the '--metadata' flag from the analysis command-line
                        for parameter in pipeline_parameters:
                            if parameter['flag'] == '--metadata':
                                pipeline_parameters.remove(parameter)

            for parameter in pipeline_parameters:
                if parameter['flag'] == '--artic_analysis_dir':
                    parameter['value'] = analysis_pipeline_input_dir
                elif parameter['flag'] == '--run_name':
                    parameter['value'] = run_id
                elif parameter['flag'] == '--metadata':
                    parameter['value'] = analysis_run_metadata_path

        elif pipeline['pipeline_name'] == 'BCCDC-PHL/ncov-recombinant-nf':
            # 2023-03-02 dfornika <dan.fornika@bccdc.ca>
            # Note: This code branch is identical to the 'BCCDC-PHL/ncov-tools-nf' branch above.
            #       We've duplicated it here to allow for any custom logic we may need later.

            # We don't include the '-nf' in the ncov-recombinant output dir
            analysis_output_dir_name = '-'.join([pipeline_short_name.removesuffix('-nf'), pipeline_minor_version, 'output'])
            artic_minor_version = ""
            for dependency in pipeline['dependencies']:
                if dependency['pipeline_name'] == 'BCCDC-PHL/ncov2019-artic-nf':
                    artic_version = dependency['pipeline_version']
                    artic_minor_version = '.'.join(artic_version.lstrip('v').split('.')[0:2])
            ncov2019_artic_nf_output_dir = "ncov2019-artic-nf-v" + artic_minor_version + "-output"
            analysis_pipeline_output_dir = os.path.abspath(os.path.join(analysis_run_output_dir, ncov2019_artic_nf_output_dir, analysis_output_dir_name))
            analysis_pipeline_input_dir = os.path.abspath(os.path.join(analysis_run_output_dir, ncov2019_artic_nf_output_dir))
            analysis_run_metadata_path = os.path.join(analysis_run_output_dir, 'metadata.tsv')

            # Need to do a separate pass over parameters specifically to
            # remove the metadata flag, to avoid mutating the list of
            # parameters while iterating over it.
            if not os.path.exists(analysis_run_metadata_path):
                for parameter in pipeline_parameters:
                    if parameter['flag'] == '--metadata':
                        pipeline_parameters.remove(parameter)

            for parameter in pipeline_parameters:
                if parameter['flag'] == '--artic_analysis_dir':
                    parameter['value'] = analysis_pipeline_input_dir
                elif parameter['flag'] == '--run_name':
                    parameter['value'] = run_id
                elif parameter['flag'] == '--metadata':
                    parameter['value'] = analysis_run_metadata_path

        else:
            # We only want to run the three pipelines listed above. Skip anything else.
            continue

        for parameter in pipeline_parameters:
            if parameter["flag"] == "--outdir":
                parameter["value"] = analysis_pipeline_output_dir

        analysis_dependencies_complete = check_analysis_dependencies_complete(pipeline, run['analysis_parameters'], analysis_run_output_dir)
        analysis_not_already_started = not os.path.exists(analysis_pipeline_output_dir)
        conditions_checked = {
            'pipeline_dependencies_met': analysis_dependencies_complete,
            'analysis_not_already_started': analysis_not_already_started,
        }
        conditions_met = list(conditions_checked.values())

        if not all(conditions_met):
            logging.warning(json.dumps({
                "event_type": "analysis_skipped",
                "pipeline_name": pipeline['pipeline_name'],
                "pipeline_version": pipeline['pipeline_version'],
                "pipeline_dependencies": pipeline['dependencies'],
                "sequencing_run_id": run_id,
                "conditions_checked": conditions_checked,
            }))
            continue

        analysis_timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        analysis_work_dir = os.path.abspath(os.path.join(base_analysis_work_dir, 'work-' + run_id + '_' + pipeline_short_name + '_' + analysis_timestamp))
        analysis_report_path = os.path.abspath(os.path.join(analysis_pipeline_output_dir, run_id + '_' + pipeline_short_name + '_report.html'))
        analysis_trace_path = os.path.abspath(os.path.join(analysis_pipeline_output_dir, run_id + '_' + pipeline_short_name + '_trace.tsv'))
        analysis_timeline_path = os.path.abspath(os.path.join(analysis_pipeline_output_dir, run_id + '_' + pipeline_short_name + '_timeline.html'))
        analysis_log_path = os.path.abspath(os.path.join(analysis_pipeline_output_dir, run_id + '_' + pipeline_short_name + '_nextflow.log'))
        pipeline_command = [
            'nextflow',
            '-log', analysis_log_path,
            'run',
            pipeline['pipeline_name'],
            '-r', pipeline['pipeline_version'],
            '-profile', 'conda',
            '--cache', os.path.join(os.path.expanduser('~'), '.conda/envs'),
            '-work-dir', analysis_work_dir,
            '-with-report', analysis_report_path,
            '-with-trace', analysis_trace_path,
            '-with-timeline', analysis_timeline_path,
        ]
        if 'send_notification_emails' in config and config['send_notification_emails']:
            pipeline_command += ['-with-notification', ','.join(notification_email_addresses)]
        for pipeline_parameter in pipeline_parameters:
            if "flag" in pipeline_parameter and "value" in pipeline_parameter:
                flag = pipeline_parameter["flag"]
                value = pipeline_parameter["value"]
                pipeline_command += [flag, value]
            elif "flag" in pipeline_parameter:
                flag = pipeline_parameter["flag"]
                pipeline_command += [flag]
            elif "value" in pipeline_parameter:
                value = pipeline_parameter["value"]
                pipeline_command += [value]
            else:
                # We should at least have a "flag" or a "value" for the parameter.
                # If we don't, ignore the parameter.
                continue

        logging.info(json.dumps({"event_type": "analysis_started", "sequencing_run_id": run_id, "pipeline_command": " ".join(pipeline_command)}))
        analysis_complete = {"timestamp_analysis_start": datetime.datetime.now().isoformat()}
        try:
            os.makedirs(analysis_work_dir)
            analysis_result = subprocess.run(pipeline_command, capture_output=True, check=True, cwd=analysis_work_dir)
            analysis_complete['timestamp_analysis_complete'] = datetime.datetime.now().isoformat()
            with open(os.path.join(analysis_pipeline_output_dir, 'analysis_complete.json'), 'w') as f:
                json.dump(analysis_complete, f, indent=2)
            logging.info(json.dumps({"event_type": "analysis_completed", "sequencing_run_id": run_id, "pipeline_command": " ".join(pipeline_command)}))
            shutil.rmtree(analysis_work_dir, ignore_errors=True)
            logging.info(json.dumps({"event_type": "analysis_work_dir_deleted", "sequencing_run_id": run_id, "analysis_work_dir_path": analysis_work_dir}))
        except subprocess.CalledProcessError as e:
            logging.error(json.dumps({"event_type": "analysis_failed", "sequencing_run_id": run_id, "pipeline_command": " ".join(pipeline_command)}))
        except OSError as e:
            logging.error(json.dumps({"event_type": "delete_analysis_work_dir_failed", "sequencing_run_id": run_id, "analysis_work_dir_path": analysis_work_dir}))

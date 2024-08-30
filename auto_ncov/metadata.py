import argparse
import csv
import glob
import json
import os
import sys

from datetime import date

import auto_ncov.config


def load_metadata(config: dict[str, object]) -> dict[str, dict[str, object]]:
    """
    Load metadata from a pre-populated metadata csv file.

    :param config: Application config. Required keys: `["metadata_file"]`.
    :type config: dict[str, object]
    :return: All available metadata, indexed by container ID
    :rtype: dict[str, dict[str, object]]
    """
    metadata = {}

    float_fields = [
        'ncov_qpcr_orf1_result',
        'ncov_qpcr_n_sarbeco_result',
        'ncov_qpcr_n2_result',
        'ncov_qpcr_e_sarbeco_result',
        'ncov_qpcr_rdrp_lee_result',
    ]

    date_fields = [
        'collection_date',
    ]

    all_containerids = set()
    if 'metadata_file' in config:
        metadata_path = config['metadata_file']
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row.pop("")
                    for field in float_fields:
                        try:
                            row[field] = float(row[field])
                            if row[field] == 0.0:
                                row[field] = None
                        except ValueError as e:
                            row[field] = None
                    for field in date_fields:
                        try:
                            row[field] = date.fromisoformat(row[field]).strftime('%Y-%m-%d')
                        except ValueError as e:
                            row[field] = None

                    metadata[row['containerid']] = row

    return metadata


def combine_ct_values(metadata: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """
    Take the available ct values and select one based on a pre-defined order of preference.

    :param metadata: Dictionary of all available metadata, indexed by container ID.
    :type metadata: dict[str, dict[str, object]]
    :return: The same metadata that is passed as input, with an additional `ct_combo` field on each metadata entry.
    :rtype: dict[str, dict[str, object]]
    """
    ct_fields_by_preference = [
        'ncov_qpcr_e_sarbeco_result',
        'ncov_qpcr_rdrp_lee_result',
        'ncov_qpcr_n2_result',
        'ncov_qpcr_n_sarbeco_result',
        'ncov_qpcr_orf1_result',
    ]

    for containerid, sample_metadata in metadata.items():
        ct_combo = None
        for ct_field in ct_fields_by_preference:
            if sample_metadata[ct_field] is not None:
                ct_combo = sample_metadata[ct_field]
                break
        
        if sample_metadata[containerid].startswith("POS"):
            sample_metadata['ct_combo'] = 0
        else:
            sample_metadata['ct_combo'] = ct_combo

    return metadata


def get_run_library_ids(config: dict[str, object], run_id: str) -> list[str]:
    """
    Iterate over fastq files in a directory. Identify all library IDs for the fastq files in the run. If an `Undetermined` fastq file is present, exclude it.
    
    :param config: Application config. Required keys: `["fastq_by_run_dir"]`.
    :type config: dict[str, object]
    :return: A list of library IDs for the run.
    :rtype: list[str]
    """
    sample_library_ids = set()
    run_fastq_dir = os.path.join(config['fastq_by_run_dir'], run_id)
    is_sample = lambda x: not(x.startswith('Undetermined'))
    if os.path.exists(run_fastq_dir):
        run_fastq_filenames = list(map(lambda x: os.path.basename(x), glob.glob(os.path.join(run_fastq_dir, '*.fastq.gz'))))
        sample_fastq_filenames = list(filter(lambda x: is_sample(x), run_fastq_filenames))
        for fastq_filename in sample_fastq_filenames:
            library_id = fastq_filename.split('_')[0]
            sample_library_ids.add(library_id)

    sample_library_ids = list(sample_library_ids)
                                  
    return sample_library_ids


def select_run_metadata(all_metadata: dict[str, dict[str, object]], run_library_ids) -> list[dict[str, object]]:
    """
    Given all available metadata and a list of library IDs for the current run, select only the metadata for the current run.
    Any library ID starting with `POS` or `NEG` will have null metadata (represented with `NA`), as these represent positive and negative controls.
    
    :param all_metadata: Dictionary, where keys are container ID and values are dictionary with keys: `["ct_combo", "collection_date"]`
    :type all_metadata: dict[str, dict[str, object]]
    :return: A list of dictionaries representing metadata for the libraries on the current run. Keys: `["sample", "ct", "date"]`
    :rtype: list[dict[str, object]]
    """
    run_metadata = []
    for library_id in run_library_ids:
        library_selected_metadata = {
            'sample': library_id,
            'ct': None,
            'date': None,
        }
        if not(library_id.startswith('POS') or library_id.startswith('NEG')):
            library_id_split = library_id.split('-')
            if len(library_id_split) > 0:
                container_id = library_id_split[0]
                try:
                    library_metadata = all_metadata[container_id]
                    library_selected_metadata = {
                        'sample': library_id,
                        'ct': library_metadata['ct_combo'],
                        'date': library_metadata['collection_date']
                    }            
                except KeyError as e:
                    pass

        run_metadata.append(library_selected_metadata)

    return run_metadata


def collect_run_metadata(config: dict[str, object], run_id: str) -> list[dict[str, object]]:
    """
    Collect the metadata needed by ncov-tools (Ct score, collection date) for a specific run.
    Metadata is collected from a pre-generated .csv file that includes metadata for all libraries.

    :param config: Application config. Required keys: `["fastq_by_run_dir", "metadata_file"]`.
    :type config: dict[str, object]
    :param run_id: The identifier for the run whose metadata is to be collected.
    :type run_id: str
    :return: A list of dictionaries representing metadata for the libraries on the current run. Keys: `["sample", "ct", "date"]`
    :rtype: list[dict[str, object]]
    """
    all_metadata = load_metadata(config)
    all_metadata_with_ct_combo = combine_ct_values(all_metadata)
    run_library_ids = get_run_library_ids(config, run_id)
    run_metadata = select_run_metadata(all_metadata_with_ct_combo, run_library_ids)

    return run_metadata


def main(args):

    config = auto_ncov.config.load_config(args.config)
    run_metadata = collect_run_metadata(config, args.run_id)
    output_fieldnames = [
        'sample',
        'ct',
        'date',
    ]

    writer = csv.DictWriter(sys.stdout, fieldnames=output_fieldnames, dialect='excel-tab')
    writer.writeheader()
    for row in run_metadata:
        for field in output_fieldnames:
            if row[field] is None:
                row[field] = "NA"
        writer.writerow(row)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')
    parser.add_argument('-r', '--run-id')
    args = parser.parse_args()
    main(args)

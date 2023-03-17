import argparse
import csv
import glob
import json
import os

import auto_ncov.config

from datetime import date


def load_metadata(config):
    """
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


def combine_ct_values(metadata):
    """
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
                ct_combo = sample_metadata['ncov_qpcr_e_sarbeco_result']
                break

        sample_metadata['ct_combo'] = ct_combo

    return metadata


def get_run_library_ids(config, run_id):
    """
    """
    sample_library_ids = []
    run_fastq_dir = os.path.join(config['fastq_by_run_dir'], run_id)
    is_sample = lambda x: not(x.startswith('Undetermined'))
    if os.path.exists(run_fastq_dir):
        run_fastq_filenames = list(map(lambda x: os.path.basename(x), glob.glob(os.path.join(run_fastq_dir, '*.fastq.gz'))))
        sample_fastq_filenames = list(filter(lambda x: is_sample(x), run_fastq_filenames))
        sample_library_ids = list(map(lambda x: x.split('_')[0], sample_fastq_filenames))
        
        print(json.dumps(sample_library_ids, indent=2))
        exit()
                                  
    return sample_library_ids
        

def main(args):
    today = date.today().strftime('%Y-%m-%d')
    config = auto_ncov.config.load_config(args.config)
    metadata = load_metadata(config)
    metadata = combine_ct_values(metadata)
    get_run_library_ids(config, args.run_id)
    print(json.dumps(list(metadata.values()), indent=2))
    
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')
    parser.add_argument('-r', '--run-id')
    args = parser.parse_args()
    main(args)

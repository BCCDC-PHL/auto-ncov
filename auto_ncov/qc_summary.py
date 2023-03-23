import argparse
import csv
import json
import os

import auto_ncov.config


def parse_ncov_tools_summary_qc(ncov_tools_summary_qc_path: str) -> list[dict[str, str]]:
    """
    Parse an ncov-tools summary_qc file.
    
    :param ncov_tools_summary_qc_path: Path to ncov-tools summary_qc file.
    :type ncovo_tools_summary_qc_path: str
    :return: Parsed ncov-tools summary_qc data
    :rtype: list[dict[str, str]]
    """
    summary_qc = []
    sample_count = 1
    with open(ncov_tools_summary_qc_path) as f:
        reader = csv.DictReader(f, dialect='excel-tab')
        for row in reader:
            row[""] = sample_count
            summary_qc.append(row)
            sample_count += 1

    return summary_qc


def add_integer_index(list_of_dicts: list[dict[str, object]]) -> list[dict[str, object]]:
    """
    Given a list of dictionaries, insert an integer index into each dict, with key "".
    This is necessary due to the established output format for QC summary files, which include
    an integer index field with an empty header. For example:

    ,sample_id,some_metric,some_other_metric,...
    1,sample-01,98.3,1,...
    2,sample-02,99.1,3,...
    3,sample-03,89.8,5,...

    :param list_of_dicts:
    :type list_of_dicts: list[dict[str, object]]
    """
    idx = 1
    for d in list_of_dicts:
        d[""] = idx
        idx += 1

    return list_of_dicts


def parse_pangolin_lineages(pangolin_lineages_path):
    """
    """
    pangolin_lineages_by_sample_id = {}
    with open(pangolin_lineages_path) as f:
        reader = csv.DictReader(f, dialect='unix')
        for row in reader:
            sample_id = row['sample_id']
            pangolin_lineages_by_sample_id[sample_id] = row

    return pangolin_lineages_by_sample_id


def join_pangolin_lineages_to_summary_qc(summary_qc, pangolin_lineages):
    """
    """
    for summary_qc_record in summary_qc:
        sample_id = summary_qc_record["sample"]
        sample_pangolin_lineages = pangolin_lineages[sample_id]
        summary_qc_record['lineage_x'] = summary_qc_record['lineage']
        summary_qc_record.pop('lineage')
        
        summary_qc_record['pangoLEARN_version'] = sample_pangolin_lineages['pangoLEARN_version']
    

def main(args):
    config = auto_ncov.config.load_config(args.config)
    ncov_tools_summary_qc_path = os.path.join(
        config['analysis_output_dir'],
        args.run_id,
        "ncov2019-artic-nf-v1.3-output",
        "ncov-tools-v1.9-output",
        "qc_reports",
        args.run_id + '_summary_qc.tsv'
    )

    if os.path.exists(ncov_tools_summary_qc_path):
        ncov_tools_summary_qc = parse_ncov_tools_summary_qc(ncov_tools_summary_qc_path)
        print(json.dumps(ncov_tools_summary_qc[0:2], indent=2))

    pangolin_lineages_path = os.path.join(
        config['analysis_output_dir'],
        args.run_id,
        "ncov2019-artic-nf-v1.3-output",
        "pangolin-nf-v0.2-output",
        "pangolin_lineages.csv"
    )

    if os.path.exists(pangolin_lineages_path):
        pangolin_lineages_by_sample_id = parse_pangolin_lineages(pangolin_lineages_path)
        print(json.dumps(list(pangolin_lineages_by_sample_id.values())[0:2], indent=2))

    output_fieldnames = [
        "",
        "sample",
        "run_name",
        "num_consensus_snvs",
        "num_consensus_n",
        "num_consensus_iupac",
        "num_variants_snvs",
        "num_variants_indel",
        "num_variants_indel_triplet",
        "mean_sequencing_depth",
        "median_sequencing_depth",
        "qpcr_ct",
        "collection_date",
        "num_weeks",
        "scaled_variants_snvs",
        "genome_completeness",
        "qc_pass_x",
        "lineage_x",
        "watch_mutations",
        "watchlist_id",
        "num_observed_mutations",
        "num_mutations_in_watchlist",
        "proportion_watchlist_mutations_observed",
        "note",
        "pangoLEARN_version",
        "pct_N_bases",
        "pct_covered_bases",
        "longest_no_N_run",
        "num_aligned_reads",
        "qc_pass_y",
        "sample_name",
    ]

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config')
    parser.add_argument('-r', '--run-id')
    args = parser.parse_args()
    main(args)

import gzip
import io
import json
import logging


def get_first_n_reads(fastq_path, num_reads):
    num_lines = num_reads * 4
    lines_read = 0
    num_reads_read = 0
    reads = []
    if fastq_path.endswith('.gz'):
        f = io.TextIOWrapper(io.BufferedReader(gzip.open(fastq_path, 'rb')))
    else:
        f = open(fastq_path, 'r')

    while num_reads_read < num_reads:
        try:
            header = next(f).strip()
            seq = next(f).strip()
            plus = next(f).strip()
            quality = next(f).strip()
            read = {
                'header': header,
                'seq': seq,
                'quality': quality,
            }
            reads.append(read)
            num_reads_read += 1
        except StopIteration as e:
            break

    f.close()
    logging.debug(json.dumps({"event_name": "sampled_reads_for_length_estimation", "fastq_path": fastq_path, "num_reads": len(reads)}))

    return reads


def estimate_read_length(reads):
    num_reads = len(reads)
    total_len_seqs = 0
    avg_read_len = 0
    estimated_read_len = 150

    for read in reads:
        total_len_seqs += len(read['seq'])
    if num_reads > 0:
        avg_read_len = total_len_seqs / num_reads

    if avg_read_len > 52 and avg_read_len < 102:
        estimated_read_len = 100
    elif avg_read_len > 102 and avg_read_len < 152:
        estimated_read_len = 150
    elif avg_read_len > 152 and avg_read_len < 202:
        estimated_read_len = 200
    elif avg_read_len > 152 and avg_read_len < 202:
        estimated_read_len = 250

    logging.debug(json.dumps({"event_name": "estimated_read_length", "num_reads": num_reads, "mean_read_length": avg_read_len, "rounded_estimated_read_length": estimated_read_len}))

    return estimated_read_len
        

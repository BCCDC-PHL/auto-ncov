# auto-ncov
Automated analysis of SARS-CoV-2 sequence data.

# Installation

```
git clone https://github.com/BCCDC-PHL/auto-ncov.git
cd auto-ncov
conda create -n auto-ncov python=3
conda activate auto-ncov
pip install .
```

# Usage
Start the tool as follows:

```bash
auto-ncov --config config.json
```

See the Configuration section of this document for details on preparing a configuration file.

More detailed logs can be produced by controlling the log level using the `--log-level` flag:

```bash
auto-ncov --config config.json --log-level debug
```

# Configuration
This tool takes a single config file, in JSON format, with the following structure:

```json
{
    "fastq_by_run_dir": "/path/to/fastq_symlinks_by_run",
    "analysis_output_dir": "/path/to/analysis_by_run",
    "analysis_work_dir": "/path/to/auto-ncov-work",
    "excluded_runs_list": "/path/to/excluded_runs.csv",
    "notification_email_addresses": [
        "someone@example.org",
        "someone_else@example.org"
    ],
    "send_notification_emails": true,
    "scan_interval_seconds": 3600,
    "pipelines": [
        {
            "pipeline_name": "BCCDC-PHL/ncov2019-artic-nf",
            "pipeline_version": "1.3.3",
            "pipeline_parameters": [
                {
                    "flag": "--illumina"
                },
                {
                    "flag": "--prefix",
                    "value": null
                },
                {
                    "flag": "--ref",
                    "value": "/path/to/artic-ncov2019/primer_schemes/nCoV-2019/V1200/nCoV-2019.reference.fasta"
                },
                {
                    "flag": "--gff",
                    "value": "/path/to/artic-ncov2019/primer_schemes/nCoV-2019/V1200/MN908947.3.gff"
                },
                {
                    "flag": "--bed",
                    "value": "/path/to/artic-ncov2019/primer_schemes/nCoV-2019/V1200/nCoV-2019.primer.bed"
                },
                {
                    "flag": "--primer_pairs_tsv",
                    "value": "/path/to/artic-ncov2019/primer_schemes/nCoV-2019/V1200/primer_pairs.tsv"
                },
                {
                    "flag": "--composite_ref",
                    "value": "/path/to/composite_GRCh38_SARS-CoV-2.fna"
                },
                {
                    "flag": "--directory",
                    "value": null
                },
                {
                    "flag": "--outdir",
                    "value": null
                }
            ],
        },
        {
            "pipeline_name": "BCCDC-PHL/ncov-tools-nf",
            "pipeline_version": "v1.5.8",
            "dependencies": [
                {
                    "pipeline_name": "BCCDC-PHL/ncov2019-artic-nf",
                    "pipeline_version": "v1.3.3"
                }
            ],
            "pipeline_parameters": [
                {
                    "flag": "--artic_analysis_dir",
                    "value": null
                },
                {
                    "flag": "--metadata",
                    "value": null
                },
                {
                    "flag": "--run_name",
                    "value": null
                },
                {
                    "flag": "--downsampled"
                },
                {
                    "flag": "--split_by_plate"
                },
                {
                    "flag": "--freebayes_consensus"
                },
                {
                    "flag": "--freebayes_variants"
                },
                {
                    "flag": "--outdir",
                    "value": null
                }
            ]
        },
		{
            "pipeline_name": "BCCDC-PHL/ncov-recombinant-nf",
            "pipeline_version": "v0.1.5",
            "dependencies": [
                {
                    "pipeline_name": "BCCDC-PHL/ncov2019-artic-nf",
                    "pipeline_version": "v1.3.3"
                }
            ],
            "pipeline_parameters": [
                {
                    "flag": "--ncov_recombinant_version",
                    "value": "0.7.0"
                },
                {
                    "flag": "--artic_analysis_dir",
                    "value": null
                },
                {
                    "flag": "--metadata",
                    "value": null
                },
                {
                    "flag": "--run_name",
                    "value": null
                },
                {
                    "flag": "--outdir",
                    "value": null
                }
            ]
        }
    ]
}
```

# Logging
This tool outputs [structured logs](https://www.honeycomb.io/blog/structured-logging-and-your-team/) in [JSON Lines](https://jsonlines.org/) format:

Every log line should include the fields:

- `timestamp`
- `level`
- `module`
- `function_name`
- `line_num`
- `message`

...and the contents of the `message` key will be a JSON object that includes at `event_type`. The remaining keys inside the `message` will vary by event type.

```json
{"timestamp": "2022-09-22T11:32:52.287", "level": "INFO", "module", "core", "function_name": "scan", "line_num", 56, "message": {"event_type": "scan_start"}}
```

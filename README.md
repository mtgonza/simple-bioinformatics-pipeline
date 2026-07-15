# simple-bioinformatics-pipeline

A containerized bioinformatics pipeline for aligning paired-end DNA sequence reads. The pipeline takes FASTQ files and a reference genome FASTA file as input, and produces coordinate-sorted BAM files as the final output using BWA and SAMtools. The pipeline is containerized with Docker, and the Python script parallel_pipeline.py runs the Docker container across four unique samples concurrently and then logs running time and CPU/memory usage.

## Pipeline



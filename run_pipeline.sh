#!/bin/bash

set -e

SAMPLE=${1:-1M_SRR9336468}

# Use the symlinks from parallel_pipeline/data/samples/
REF="/project/data/Saccharomyces_cerevisiae.R64-1-1.dna.toplevel.fa"
R1="/project/parallel_pipeline/data/samples/${SAMPLE}_R1.fastq"
R2="/project/parallel_pipeline/data/samples/${SAMPLE}_R2.fastq"

echo "Starting alignment pipeline for sample: ${SAMPLE}"
echo "Reference: $REF"
echo "R1: $R1"
echo "R2: $R2"

# Step 1: Index reference genome (ONLY if not already indexed)
if [ ! -f "${REF}.bwt" ]; then
    echo "Step 1: Indexing reference genome..."
    bwa index $REF
else
    echo "Step 1: Reference already indexed, skipping..."
fi

echo "Step 2: Aligning reads to reference..."
bwa mem $REF $R1 $R2 > ${SAMPLE}.sam

echo "Step 3: Converting SAM to BAM..."
samtools view -S -b ${SAMPLE}.sam > ${SAMPLE}.bam

echo "Step 4: Sorting BAM file..."
samtools sort ${SAMPLE}.bam -o ${SAMPLE}_sorted.bam

echo "Step 5: Removing intermediate SAM file..."
rm ${SAMPLE}.sam

echo "Pipeline complete! Final output: ${SAMPLE}_sorted.bam"
ls -lh ${SAMPLE}_sorted.bam

#!/usr/bin/env python3

# Parallel Pipeline Processor
# runs multiple Docker containers in parallel for different samples

import os
import subprocess
import multiprocessing
import time
import logging
import psutil
from datetime import datetime
from pathlib import Path
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed # use ProcessPoolExecutor for better error handling

# ============================================
# CONFIGURATION 
# ============================================
NUM_WORKERS = 4
SAMPLES_DIR = "data/samples"
RESULTS_DIR = "results"
LOGS_DIR = "logs"
REFERENCE =  "../data/Saccharomyces_cerevisiae.R64-1-1.dna.toplevel.fa" # reference genome
DOCKER_IMAGE = "genomics-toolbox:v1"
PIPELINE_SCRIPT = "../run_pipeline.sh"

# ============================================
# LOGGING SETUP
# ============================================
def setup_logging(sample_id):
    # create log file for sample
    os.makedirs(LOGS_DIR, exist_ok=True)
    log_file = f"{LOGS_DIR}/{sample_id}_pipeline.log"

    # create a logger for this sample
    logger = logging.getLogger(sample_id)
    logger.setLevel(logging.INFO)

    # file handler
    file_handler = logging.FileHandler(log_file)
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)

    # print logs to console
    console_handler = logging.StreamHandler()
    console_log_format = '%(asctime)s - %(name)s - %(message)s'
    console_handler.setFormatter(logging.Formatter(console_log_format))
    logger.addHandler(console_handler)

    return logger


# ============================================
# SYSTEM MONITORING
# ============================================
def get_cpu_usage():
    # get current CPU usage percentage
    try:
        return psutil.cpu_percent(interval=0.1)
    except:
        return 0.0

def get_memory_usage():
    # get current memory usage percentage
    try:
        return psutil.virtual_memory().percent
    except:
        return 0.0


# ============================================
# SAMPLE PROCESSING FUNCTION
# ============================================
def process_sample(sample_name):
    # process a single sample using Docker container
    # this function runs in a separate process

    # set up logging for the sample
    logger = setup_logging(sample_name)

    # record start time and system resources before processing
    start_time = time.time()
    start_datetime = datetime.now().isoformat()
    start_cpu = get_cpu_usage()
    start_memory = get_memory_usage()

    logger.info(f"🚀 STARTING processing for sample: {sample_name}")
    logger.info(f"   Start time: {start_datetime}")
    logger.info(f"   CPU usage at start: {start_cpu}%")
    logger.info(f"   Memory usage at start: {start_memory}%")

    r1 = f"{SAMPLES_DIR}/{sample_name}_R1.fastq"
    r2 = f"{SAMPLES_DIR}/{sample_name}_R2.fastq"
    output_dir = f"{RESULTS_DIR}/{sample_name}"

    # check if input files exist
    if not os.path.exists(r1) or not os.path.exists(r2):
        logger.error(f"❌ Missing input files for {sample_name}")
        logger.error(f"   Expected: {r1} and {r2}")
        return {
            "sample": sample_name,
            "status": "FAILED",
            "error": "Input files not found",
            "start_time": start_datetime,
            "end_time": datetime.now().isoformat()
        }

    #create output directory
    os.makedirs(output_dir, exist_ok=True)

    # build docker command
    # we mount the project root so the container can access everything
    project_root = os.path.abspath("..")

    # for each sample, we run the pipeline with the sample name as argument
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{project_root}:/project",
        "-w", f"/project/parallel_pipeline",
        DOCKER_IMAGE,
        "bash", "-c",
        f"""
        set -e

        echo "Processing samples: {sample_name}"
        echo "R1: {r1}"
        echo "R2: {r2}"

        # run the pipeline with sample name
        bash {PIPELINE_SCRIPT} {sample_name}

        # move results to sample-specific folder
        mkdir -p /project/parallel_pipeline/{RESULTS_DIR}/{sample_name}
        mv /project/parallel_pipeline/{sample_name}_sorted.bam /project/parallel_pipeline/{RESULTS_DIR}/{sample_name}/
        mv /project/parallel_pipeline/{sample_name}.bam /project/parallel_pipeline/{RESULTS_DIR}/{sample_name}/ 2>/dev/null || true
        """
    ]

    logger.info(f"  Running Docker command: {' '.join(docker_cmd[:5])}...")

    try:
        # execute the Docker command
        process = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        # record end time
        end_time = time.time()
        end_datetime = datetime.now().isoformat()
        end_cpu = get_cpu_usage()
        end_memory = get_memory_usage()
        duration = end_time - start_time

        # check if successful
        if process.returncode == 0:
            logger.info(f"✅ SUCCESS: Sample {sample_name} completed!")
            status = "SUCCESS"
        else:
            logger.error(f"❌ FAILED: Sample {sample_name} had errors!")
            logger.error(f"   Return code: {process.returncode}")
            if process.stderr:
                logger.error(f"   Error output: {process.stderr[:500]}...")
            status = "FAILED"

        # Log duration
        logger.info(f"   Duration: {duration:.2f} seconds")
        logger.info(f"   End time: {end_datetime}")
        logger.info(f"   CPU usage at end: {end_cpu}%")
        logger.info(f"   Memory usage at end: {end_memory}%")

        # return results as dictionary
        return {
            "sample": sample_name,
            "status": status,
            "duration": duration,
            "start_time": start_datetime,
            "end_time": end_datetime,
            "start_cpu": start_cpu,
            "end_cpu": end_cpu,
            "start_memory": start_memory,
            "end_memory": end_memory,
            "return_code": process.returncode,
            "stdout": process.stdout[:1000] if process.stdout else "",
            "stderr": process.stderr[:1000] if process.stderr else ""
        }

    except subprocess.TimeoutExpired:
        logger.error(f"⏰ TIMEOUT: Sample {sample_name} took too long!")
        return {
            "sample": sample_name,
            "status": "TIMEOUT",
            "duration": 600,
            "start_time": start_datetime,
            "end_time": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"💥 ERROR: {str(e)}")
        return {
            "sample": sample_name,
            "status": "ERROR",
            "error": str(e),
            "start_time": start_datetime,
            "end_time": datetime.now().isoformat()
        }


# ============================================
# FIND SAMPLES
# ============================================
def find_samples():
    """Find all sample pairs in the samples directory"""
    samples = []
    sample_dir = Path(SAMPLES_DIR)
    
    if not sample_dir.exists():
        print(f"❌ Error: Samples directory '{SAMPLES_DIR}' not found!")
        print(f"   Please create it with symlinks to your data.")
        return samples
    
    # Look for files ending with _R1.fastq
    for r1_file in sample_dir.glob("*_R1.fastq"):
        # Extract sample name (remove _R1.fastq)
        sample_name = r1_file.stem.replace("_R1", "")
        r2_file = sample_dir / f"{sample_name}_R2.fastq"
        
        if r2_file.exists():
            samples.append(sample_name)
            print(f"📊 Found sample: {sample_name}")
        else:
            print(f"⚠️  Warning: Missing R2 file for {sample_name}")
    
    return samples

# ============================================
# MAIN FUNCTION
# ============================================
def main():
    # main function to run parallel processing
    print("=" * 70)
    print("🔬 PARALLEL PIPELINE PROCESSOR")
    print("=" * 70)
    print(f"📁 Project directory: {os.getcwd()}")
    print(f"🔢 Workers: {NUM_WORKERS}")
    print(f"🐳 Docker image: {DOCKER_IMAGE}")
    print("=" * 70)
    
    # check Docker is running
    try:
        subprocess.run(["docker", "ps"], capture_output=True, check=True)
    except:
        print("❌ Docker is not running! Please start Docker.")
        print("   Try: sudo service docker start")
        sys.exit(1)
    
    # find samples
    samples = find_samples()
    if not samples:
        print("❌ No samples found! Exiting.")
        print("   Make sure you have symlinks in data/samples/")
        sys.exit(1)
    
    print(f"\n📊 Found {len(samples)} samples:")
    for s in samples:
        print(f"   - {s}")
    print()
    
    # create results directory
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # process samples in parallel
    start_total = time.time()
    
    print("🚀 Starting parallel processing...")
    print(f"   Processing {len(samples)} samples with {NUM_WORKERS} workers\n")
    print("=" * 70)
    
    # submit all tasks
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_sample = {
            executor.submit(process_sample, sample): sample 
            for sample in samples
        }
        
        # collect results as they complete
        results = []
        completed = 0
        total = len(samples)
        
        for future in as_completed(future_to_sample):
            sample = future_to_sample[future]
            completed += 1
            
            try:
                result = future.result(timeout=700)  # 12 minute timeout per process
                results.append(result)
                
                # print progress
                print(f"\n📊 Progress: {completed}/{total} complete")
                
                # show quick status
                status = result.get("status", "UNKNOWN")
                duration = result.get("duration", 0)
                icon = "✅" if status == "SUCCESS" else "❌" if status == "FAILED" else "⚠️"
                print(f"   {icon} {sample}: {status} ({duration:.1f}s)")
                
            except Exception as e:
                print(f"💥 Worker for {sample} crashed: {str(e)}")
                results.append({
                    "sample": sample,
                    "status": "CRASHED",
                    "error": str(e)
                })
    
    end_total = time.time()
    total_duration = end_total - start_total
    
    # save summary
    summary = {
        "total_samples": len(samples),
        "total_duration": total_duration,
        "workers": NUM_WORKERS,
        "docker_image": DOCKER_IMAGE,
        "results": results,
        "timestamp": datetime.now().isoformat()
    }
    
    # write summary to file
    with open(f"{RESULTS_DIR}/summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # print final summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"Total samples processed: {len(results)}")
    print(f"Total time: {total_duration:.2f} seconds")
    print(f"Average time per sample: {total_duration/len(results):.2f} seconds")
    print()
    
    # count statuses
    status_counts = {}
    for r in results:
        status = r.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("Status breakdown:")
    for status, count in status_counts.items():
        icon = "✅" if status == "SUCCESS" else "❌" if status == "FAILED" else "⚠️"
        print(f"   {icon} {status}: {count}")
    
    print(f"\n📁 Results saved to: {RESULTS_DIR}/")
    print(f"   - summary.json (full details)")
    print(f"   - each sample has its own folder with BAM files")
    print(f"📁 Logs saved to: {LOGS_DIR}/")
    print("=" * 70)

# ============================================
# ENTRY POINT
# ============================================
if __name__ == "__main__":
    main()
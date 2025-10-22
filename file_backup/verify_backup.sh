#!/bin/bash

# Paths - EDIT THESE
OLD_SSD="/mnt/old-ssd/home/jack"  # Change this to where your old SSD is mounted
NAS_BACKUP="/mnt/nas/Backup"  # Change this to your NAS backup location
LOG_DIR="./backup_verification"

# Create log directory
mkdir -p "$LOG_DIR"

# Timestamp for this run
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/verification_$TIMESTAMP.log"

echo "===== Backup Verification Started: $(date) =====" | tee -a "$LOG_FILE"
echo "Old SSD: $OLD_SSD" | tee -a "$LOG_FILE"
echo "NAS Backup: $NAS_BACKUP" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Step 1: Count files
echo "Step 1: Counting files..." | tee -a "$LOG_FILE"
SSD_COUNT=$(find "$OLD_SSD" -type f 2>/dev/null | wc -l)
NAS_COUNT=$(find "$NAS_BACKUP" -type f 2>/dev/null | wc -l)

echo "Files on old SSD: $SSD_COUNT" | tee -a "$LOG_FILE"
echo "Files on NAS: $NAS_COUNT" | tee -a "$LOG_FILE"

if [ "$SSD_COUNT" -eq "$NAS_COUNT" ]; then
    echo "✓ File counts match!" | tee -a "$LOG_FILE"
else
    echo "✗ WARNING: File counts don't match!" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Step 2: Compare sizes
echo "Step 2: Comparing total sizes..." | tee -a "$LOG_FILE"
SSD_SIZE=$(du -sb "$OLD_SSD" 2>/dev/null | cut -f1)
NAS_SIZE=$(du -sb "$NAS_BACKUP" 2>/dev/null | cut -f1)

echo "Old SSD size: $SSD_SIZE bytes ($(du -sh "$OLD_SSD" 2>/dev/null | cut -f1))" | tee -a "$LOG_FILE"
echo "NAS size: $NAS_SIZE bytes ($(du -sh "$NAS_BACKUP" 2>/dev/null | cut -f1))" | tee -a "$LOG_FILE"

if [ "$SSD_SIZE" -eq "$NAS_SIZE" ]; then
    echo "✓ Sizes match!" | tee -a "$LOG_FILE"
else
    echo "✗ WARNING: Sizes don't match!" | tee -a "$LOG_FILE"
fi
echo "" | tee -a "$LOG_FILE"

# Step 3: Generate checksums
echo "Step 3: Generating checksums (this will take a while)..." | tee -a "$LOG_FILE"

echo "  Hashing old SSD files..." | tee -a "$LOG_FILE"
find "$OLD_SSD" -type f -exec md5sum {} + 2>/dev/null | \
    sed "s|$OLD_SSD||g" | sort > "$LOG_DIR/ssd_checksums.txt"

echo "  Hashing NAS backup files..." | tee -a "$LOG_FILE"
find "$NAS_BACKUP" -type f -exec md5sum {} + 2>/dev/null | \
    sed "s|$NAS_BACKUP||g" | sort > "$LOG_DIR/nas_checksums.txt"

echo "  Checksums saved to:" | tee -a "$LOG_FILE"
echo "    $LOG_DIR/ssd_checksums.txt" | tee -a "$LOG_FILE"
echo "    $LOG_DIR/nas_checksums.txt" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Step 4: Compare checksums
echo "Step 4: Comparing checksums..." | tee -a "$LOG_FILE"
DIFF_OUTPUT=$(diff "$LOG_DIR/ssd_checksums.txt" "$LOG_DIR/nas_checksums.txt")

if [ -z "$DIFF_OUTPUT" ]; then
    echo "✓ SUCCESS: All files match perfectly!" | tee -a "$LOG_FILE"
else
    echo "✗ DIFFERENCES FOUND:" | tee -a "$LOG_FILE"
    echo "$DIFF_OUTPUT" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
    echo "Differences saved to: $LOG_DIR/differences_$TIMESTAMP.txt" | tee -a "$LOG_FILE"
    echo "$DIFF_OUTPUT" > "$LOG_DIR/differences_$TIMESTAMP.txt"
fi

echo "" | tee -a "$LOG_FILE"
echo "===== Verification Complete: $(date) =====" | tee -a "$LOG_FILE"
echo "Full log saved to: $LOG_FILE" | tee -a "$LOG_FILE"

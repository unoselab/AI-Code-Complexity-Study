#!/bin/bash

OUTPUT_FILE="run-py-all-scripts.sh"

echo "#!/bin/bash" > "$OUTPUT_FILE"
echo "# Consolidated execution script generated on $(date)" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

for file in run-py-*; do
    if [ -f "$file" ] && [ "$file" != "$OUTPUT_FILE" ] && [ "$file" != "run-py-all-scripts-merge.sh" ]; then
        echo "Processing: $file"
        
        echo "###############################################################################" >> "$OUTPUT_FILE"
        echo "# FILE: $file" >> "$OUTPUT_FILE"
        echo "###############################################################################" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
        
        # Append the actual contents of the file, skipping its own shebang if present
        grep -v '^#!/bin/bash' "$file" >> "$OUTPUT_FILE"
        
        echo "" >> "$OUTPUT_FILE"
        echo "" >> "$OUTPUT_FILE"
    fi
done

echo "Success! All scripts merged into $OUTPUT_FILE"
chmod +x "$OUTPUT_FILE"
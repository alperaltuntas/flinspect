# Generate _ptree files for all the *.f90 files in the current directory using:
#   flang -fdebug-dump-parse-tree-no-sema [FILENAME].f90 > [FILENAME]_ptree
# This script assumes that the flang compiler is available in the system's PATH.

for file in *.f90; do
    if [ -f "$file" ]; then
        output_file="${file%.f90}_ptree"
        flang -fc1 -fdebug-dump-parse-tree-no-sema "$file" > "$output_file"
        echo "Generated $output_file from $file"
    fi
done
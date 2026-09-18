import pandas as pd
import numpy as np
import json
import os
import argparse
import logging
from tqdm import tqdm
import chardet
import csv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dataset_cleaner.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class SaaSDatasetCleaner:
    """
    Class for cleaning and validating the SaaS sales conversation dataset.
    Handles issues resulting from interrupted generations.
    """
    
    def __init__(self, input_file, output_file=None, chunk_size=1000, encoding='utf-8', skip_encoding_check=False):
        """
        Initialize the cleaner.
        
        Args:
            input_file: Path to the input CSV file
            output_file: Path to save cleaned dataset (defaults to 'cleaned_' + input_file)
            chunk_size: Number of rows to process at once
            encoding: File encoding (defaults to utf-8)
            skip_encoding_check: Whether to skip encoding detection and line-by-line processing
        """
        self.input_file = input_file
        self.output_file = output_file or f"cleaned_{os.path.basename(input_file)}"
        self.chunk_size = chunk_size
        self.encoding = encoding
        self.skip_encoding_check = skip_encoding_check
        self.stats = {
            'total_rows': 0,
            'valid_rows': 0,
            'invalid_json': 0,
            'missing_values': 0,
            'invalid_embeddings': 0,
            'duplicates': 0,
            'encoding_errors': 0,
            'recovered_rows': 0
        }
        
        # If not skipping encoding check, detect encoding
        if not self.skip_encoding_check and not self.encoding:
            self.detect_encoding()
        
        # Get the columns and prepare for processing
        self.initialize_columns()
    
    def detect_encoding(self):
        """Detect the file encoding."""
        logger.info("Detecting file encoding...")
        
        # Read a sample of the file to detect encoding
        with open(self.input_file, 'rb') as f:
            sample = f.read(min(10000000, os.path.getsize(self.input_file)))  # Read up to 10MB
        
        result = chardet.detect(sample)
        self.encoding = result['encoding']
        confidence = result['confidence']
        
        logger.info(f"Detected encoding: {self.encoding} with confidence: {confidence:.2f}")
        
        # If confidence is low, try common encodings
        if confidence < 0.7:
            logger.warning(f"Low confidence in encoding detection. Will try multiple encodings.")
            self.encoding = None  # Will try multiple encodings later
    
    def initialize_columns(self):
        """Initialize column information."""
        # Try to read the header with different encodings if needed
        encodings_to_try = ['utf-8'] if (self.skip_encoding_check or self.encoding) else ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
        
        for enc in encodings_to_try:
            try:
                # Try to read just the header
                with open(self.input_file, 'r', encoding=enc, errors='replace') as f:
                    reader = csv.reader(f)
                    self.columns = next(reader)
                
                self.encoding = enc
                logger.info(f"Successfully read header with encoding: {enc}")
                
                # Identify embedding columns
                self.embedding_cols = [col for col in self.columns if col.startswith('embedding_')]
                logger.info(f"Found {len(self.embedding_cols)} embedding columns")
                
                return
                
            except Exception as e:
                logger.warning(f"Failed to read header with encoding {enc}: {str(e)}")
        
        # If we get here, all encodings failed
        logger.error("Could not read column headers with any encoding")
        self.columns = []
        self.embedding_cols = []
    
    def process_line_by_line(self):
        """Process the file line by line to handle encoding issues."""
        logger.info("Processing file line by line to handle encoding issues...")
        
        # Open the output file
        with open(self.output_file, 'w', encoding='utf-8', newline='') as out_file:
            writer = None  # Will initialize after getting headers
            
            # Process the input file
            with open(self.input_file, 'rb') as in_file:
                # Process line by line
                line_count = 0
                valid_count = 0
                
                for line in tqdm(in_file, desc="Reading lines"):
                    line_count += 1
                    
                    # Try to decode with multiple encodings
                    decoded_line = None
                    for enc in ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']:
                        try:
                            decoded_line = line.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if decoded_line is None:
                        # Could not decode with any encoding, skip line
                        self.stats['encoding_errors'] += 1
                        continue
                    
                    # Parse the CSV line
                    try:
                        reader = csv.reader([decoded_line])
                        row = next(reader)
                        
                        # Initialize writer with headers if this is the first line
                        if line_count == 1:
                            writer = csv.writer(out_file)
                            writer.writerow(row)  # Write headers
                            continue
                        
                        # Basic validation - check number of columns
                        if len(row) != len(self.columns):
                            logger.debug(f"Line {line_count}: Column count mismatch. Expected {len(self.columns)}, got {len(row)}")
                            continue
                        
                        # Write the row
                        writer.writerow(row)
                        valid_count += 1
                        
                    except Exception as e:
                        logger.debug(f"Error processing line {line_count}: {str(e)}")
                        self.stats['encoding_errors'] += 1
            
            self.stats['total_rows'] = line_count - 1  # Subtract header
            self.stats['recovered_rows'] = valid_count
            
            logger.info(f"Processed {line_count} lines, recovered {valid_count} valid rows")
            logger.info(f"Found {self.stats['encoding_errors']} lines with encoding errors")
    
    def _validate_json_fields(self, df):
        """Validate and clean JSON fields."""
        # List of columns that should contain JSON
        json_columns = ['scenario', 'conversation', 'probability_trajectory']
        
        for col in json_columns:
            if col not in df.columns:
                continue
                
            # Create a valid indicator
            df[f'{col}_valid'] = True
            
            # Check each value
            for idx, value in enumerate(df[col]):
                try:
                    if pd.isna(value):
                        df.at[idx, f'{col}_valid'] = False
                        self.stats['invalid_json'] += 1
                        continue
                    
                    # Attempt to parse JSON
                    json.loads(value)
                except:
                    df.at[idx, f'{col}_valid'] = False
                    self.stats['invalid_json'] += 1
        
        # Create an overall valid flag
        valid_flags = [f'{col}_valid' for col in json_columns if f'{col}_valid' in df.columns]
        if valid_flags:
            df['json_valid'] = df[valid_flags].all(axis=1)
        else:
            df['json_valid'] = True
            
        # Clean up the temporary columns
        for col in json_columns:
            if f'{col}_valid' in df.columns:
                df = df.drop(columns=[f'{col}_valid'])
                
        return df
    
    def _validate_embeddings(self, df):
        """Check if embeddings are valid."""
        if not self.embedding_cols:
            return df
        
        # Check if the first embedding column has a value as a simple check
        if 'embedding_0' in df.columns:
            df['embeddings_valid'] = ~df['embedding_0'].isna()
        else:
            df['embeddings_valid'] = True
            
        # Count invalid embeddings
        self.stats['invalid_embeddings'] += (~df['embeddings_valid']).sum()
            
        return df
    
    def _check_missing_values(self, df):
        """Check for missing values in important columns."""
        important_cols = [
            'company_id', 'company_name', 'product_name', 'conversation_id', 
            'conversation', 'full_text', 'outcome'
        ]
        
        # Filter to columns that actually exist
        important_cols = [col for col in important_cols if col in df.columns]
        
        if not important_cols:
            df['missing_important'] = False
            return df
        
        # Create a flag for rows with missing important values
        missing_flags = df[important_cols].isna().any(axis=1)
        df['missing_important'] = missing_flags
        
        # Count missing values
        self.stats['missing_values'] += missing_flags.sum()
        
        return df
    
    def _flag_valid_rows(self, df):
        """Create a single flag for valid rows."""
        # A row is valid if it has valid JSON, valid embeddings, and no missing important values
        required_flags = []
        
        if 'json_valid' in df.columns:
            required_flags.append('json_valid')
            
        if 'embeddings_valid' in df.columns:
            required_flags.append('embeddings_valid')
            
        if 'missing_important' in df.columns:
            required_flags.append('~missing_important')
        
        if required_flags:
            if '~missing_important' in required_flags:
                required_flags.remove('~missing_important')
                if required_flags:
                    df['row_valid'] = df[required_flags].all(axis=1) & ~df['missing_important']
                else:
                    df['row_valid'] = ~df['missing_important']
            else:
                df['row_valid'] = df[required_flags].all(axis=1)
        else:
            df['row_valid'] = True
        
        # Update valid rows count
        self.stats['valid_rows'] += df['row_valid'].sum()
        
        return df
    
    def _remove_duplicates(self, df):
        """Remove duplicate conversation IDs."""
        if 'conversation_id' in df.columns:
            # Check for duplicates
            dup_mask = df.duplicated(subset=['conversation_id'], keep='first')
            df['is_duplicate'] = dup_mask
            
            # Count duplicates
            self.stats['duplicates'] += dup_mask.sum()
        else:
            df['is_duplicate'] = False
            
        return df
    
    def clean_dataset(self):
        """
        Clean the dataset by first fixing encoding issues, then cleaning the data.
        """
        logger.info(f"Starting to clean dataset: {self.input_file}")
        
        # Check if the file exists
        if not os.path.exists(self.input_file):
            logger.error(f"Input file not found: {self.input_file}")
            return
        
        # If we're not skipping encoding checks, process line by line
        if not self.skip_encoding_check:
            self.process_line_by_line()
            intermediate_file = self.output_file
            self.output_file = f"validated_{os.path.basename(self.input_file)}"
        else:
            logger.info("Skipping encoding check as requested")
            # Use the input file directly as the intermediate file
            intermediate_file = self.input_file
            
            # Count rows in the file for progress tracking
            with open(intermediate_file, 'r', encoding=self.encoding) as f:
                self.stats['total_rows'] = sum(1 for _ in f) - 1  # Subtract header
                self.stats['recovered_rows'] = self.stats['total_rows']
                
            logger.info(f"Total rows to validate: {self.stats['total_rows']}")
        
        # Now that we have a cleaned file with proper encoding, process it for data validation
        logger.info("Beginning data validation on recovered rows...")
        
        # Get the total number of rows for progress tracking
        try:
            total_rows = self.stats['recovered_rows']
            logger.info(f"Total rows to validate: {total_rows}")
        except Exception as e:
            logger.error(f"Error counting rows: {str(e)}")
            total_rows = 0
        
        # Process the dataset in chunks
        try:
            # Create a reader - now with known proper encoding
            # Use error_bad_lines=False for older pandas versions (renamed to on_bad_lines in newer versions)
            reader = pd.read_csv(
                intermediate_file, 
                chunksize=self.chunk_size,
                encoding='utf-8',
                low_memory=False,  # Avoid dtype warnings
                error_bad_lines=False  # Skip bad lines (older parameter name)
            )
            
            # Create a header flag for the first chunk
            first_chunk = True
            
            # Process each chunk
            with tqdm(total=total_rows, desc="Validating data") as pbar:
                for chunk_num, chunk in enumerate(reader):
                    logger.debug(f"Processing chunk {chunk_num+1}")
                    
                    # Run validation steps
                    chunk = self._validate_json_fields(chunk)
                    chunk = self._validate_embeddings(chunk)
                    chunk = self._check_missing_values(chunk)
                    chunk = self._remove_duplicates(chunk)
                    chunk = self._flag_valid_rows(chunk)
                    
                    # Filter to valid rows only
                    valid_chunk = chunk[chunk['row_valid'] & ~chunk['is_duplicate']]
                    
                    # Remove the validation columns
                    for col in ['json_valid', 'embeddings_valid', 'missing_important', 'row_valid', 'is_duplicate']:
                        if col in valid_chunk.columns:
                            valid_chunk = valid_chunk.drop(columns=[col])
                    
                    # Write the cleaned chunk
                    valid_chunk.to_csv(
                        self.output_file,
                        mode='w' if first_chunk else 'a',
                        header=first_chunk,
                        index=False,
                        encoding='utf-8'
                    )
                    
                    # Update the first chunk flag
                    if first_chunk:
                        first_chunk = False
                    
                    # Update progress
                    pbar.update(len(chunk))
            
            logger.info(f"Dataset cleaning complete. Results saved to {self.output_file}")
            
            # Print statistics
            logger.info(f"Cleaning Statistics:")
            logger.info(f"- Total rows processed: {self.stats['total_rows']}")
            logger.info(f"- Rows recovered from encoding issues: {self.stats['recovered_rows']}")
            logger.info(f"- Encoding errors: {self.stats['encoding_errors']}")
            logger.info(f"- Valid rows after validation: {self.stats['valid_rows']}")
            logger.info(f"- Rows with invalid JSON: {self.stats['invalid_json']}")
            logger.info(f"- Rows with missing values: {self.stats['missing_values']}")
            logger.info(f"- Rows with invalid embeddings: {self.stats['invalid_embeddings']}")
            logger.info(f"- Duplicate rows: {self.stats['duplicates']}")
            
            # Create a summary file
            with open(f"{self.output_file}_summary.txt", 'w') as f:
                f.write("Dataset Cleaning Summary\n")
                f.write("=======================\n\n")
                f.write(f"Input file: {self.input_file}\n")
                f.write(f"Output file: {self.output_file}\n\n")
                f.write(f"Total rows processed: {self.stats['total_rows']}\n")
                f.write(f"Rows recovered from encoding issues: {self.stats['recovered_rows']}\n")
                f.write(f"Encoding errors: {self.stats['encoding_errors']}\n")
                f.write(f"Valid rows after validation: {self.stats['valid_rows']}\n")
                f.write(f"Rows with invalid JSON: {self.stats['invalid_json']}\n")
                f.write(f"Rows with missing values: {self.stats['missing_values']}\n")
                f.write(f"Rows with invalid embeddings: {self.stats['invalid_embeddings']}\n")
                f.write(f"Duplicate rows: {self.stats['duplicates']}\n")
            
            return self.stats
            
        except Exception as e:
            logger.error(f"Error validating dataset: {str(e)}")
            raise e

def main():
    """Main function to run the dataset cleaner."""
    parser = argparse.ArgumentParser(description="Clean and validate SaaS sales conversation dataset")
    parser.add_argument("input_file", type=str, help="Path to the input CSV file")
    parser.add_argument("--output_file", type=str, default=None, 
                       help="Path to save cleaned dataset (defaults to 'cleaned_' + input_file)")
    parser.add_argument("--chunk_size", type=int, default=1000,
                       help="Number of rows to process at once")
    parser.add_argument("--encoding", type=str, default='utf-8',
                       help="File encoding (defaults to utf-8)")
    parser.add_argument("--skip_encoding_check", action="store_true",
                       help="Skip encoding detection and line-by-line processing")
    
    args = parser.parse_args()
    
    # Create and run the cleaner
    cleaner = SaaSDatasetCleaner(
        input_file=args.input_file,
        output_file=args.output_file,
        chunk_size=args.chunk_size,
        encoding=args.encoding,
        skip_encoding_check=args.skip_encoding_check
    )
    
    cleaner.clean_dataset()

if __name__ == "__main__":
    main()
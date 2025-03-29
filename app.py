from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS
import os
from pathlib import Path
from datetime import datetime
import mimetypes
import logging
import glob
import hashlib
import shutil

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

def get_file_type(file_path):
    try:
        # Get the file extension
        ext = os.path.splitext(file_path)[1].lower()
        # Get MIME type based on extension
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "Unknown"
    except Exception as e:
        logger.error(f"Error getting file type for {file_path}: {str(e)}")
        return "Unknown"

def get_file_category(file_type):
    file_type = str(file_type).lower()
    if any(keyword in file_type for keyword in ['text', 'document', 'pdf', 'word', 'excel', 'powerpoint']):
        return 'Documents'
    elif any(keyword in file_type for keyword in ['image', 'png', 'jpeg', 'jpg', 'gif', 'bmp']):
        return 'Images'
    elif any(keyword in file_type for keyword in ['video', 'mp4', 'avi', 'mov', 'wmv']):
        return 'Videos'
    elif any(keyword in file_type for keyword in ['audio', 'mp3', 'wav', 'ogg', 'm4a']):
        return 'Audio'
    elif any(keyword in file_type for keyword in ['zip', 'rar', '7z', 'tar', 'gz']):
        return 'Archives'
    else:
        return 'Others'

def analyze_directory(directory):
    files = []
    categories = {
        'Documents': [],
        'Images': [],
        'Videos': [],
        'Audio': [],
        'Archives': [],
        'Others': []
    }
    
    try:
        # Convert to Path object and resolve any relative paths
        dir_path = Path(directory).resolve()
        logger.info(f"Analyzing directory: {dir_path}")
        
        if not dir_path.exists():
            logger.error(f"Directory does not exist: {dir_path}")
            raise Exception(f"Directory does not exist: {directory}")
            
        if not dir_path.is_dir():
            logger.error(f"Path is not a directory: {dir_path}")
            raise Exception(f"Path is not a directory: {directory}")

        # Use os.walk for better Windows compatibility
        for root, dirs, filenames in os.walk(directory):
            logger.info(f"Scanning directory: {root}")
            logger.info(f"Found {len(filenames)} files in {root}")
            
            for filename in filenames:
                try:
                    file_path = os.path.join(root, filename)
                    logger.debug(f"Processing file: {file_path}")
                    
                    if os.path.isfile(file_path):
                        file_type = get_file_type(file_path)
                        category = get_file_category(file_type)
                        modified_time = os.path.getmtime(file_path)
                        file_info = {
                            'name': filename,
                            'path': file_path,
                            'type': file_type,
                            'size': os.path.getsize(file_path),
                            'modified': datetime.fromtimestamp(modified_time).strftime('%Y-%m-%d %H:%M:%S'),
                            'modified_timestamp': modified_time  # Add timestamp for sorting
                        }
                        categories[category].append(file_info)
                        files.append(file_info)
                        logger.debug(f"Added file: {filename} to category: {category}")
                except Exception as e:
                    logger.error(f"Error processing file {filename}: {str(e)}")
                    continue
        
        # Sort files in each category by modification date (newest first)
        for category in categories:
            categories[category].sort(key=lambda x: x['modified_timestamp'], reverse=True)
        
        # Sort all files by modification date (newest first)
        files.sort(key=lambda x: x['modified_timestamp'], reverse=True)
                    
        logger.info(f"Total files processed: {len(files)}")
        if not files:
            logger.warning(f"No files found in directory: {directory}")
            
    except Exception as e:
        logger.error(f"Error analyzing directory: {str(e)}")
        raise
    
    return {'files': files, 'categories': categories}

@app.route('/')
def index():
    initial_data = {
        'files': [],
        'categories': {
            'Documents': [],
            'Images': [],
            'Videos': [],
            'Audio': [],
            'Archives': [],
            'Others': []
        }
    }
    return render_template('index.html', **initial_data)

@app.route('/api/analyze', methods=['POST'])
def analyze():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        directory = data.get('directory')
        if not directory:
            return jsonify({'error': 'No directory provided'}), 400
            
        # Normalize the directory path
        directory = os.path.normpath(directory)
        logger.info(f"Received directory path: {directory}")
        
        if not os.path.exists(directory):
            logger.error(f"Directory does not exist: {directory}")
            return jsonify({'error': f'Directory does not exist: {directory}'}), 404
            
        if not os.path.isdir(directory):
            logger.error(f"Path is not a directory: {directory}")
            return jsonify({'error': f'Path is not a directory: {directory}'}), 400
            
        result = analyze_directory(directory)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in analyze endpoint: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<path:filepath>')
def get_file(filepath):
    try:
        # Normalize the file path
        filepath = os.path.normpath(filepath)
        logger.info(f"Requested file: {filepath}")
        
        if not os.path.exists(filepath):
            logger.error(f"File does not exist: {filepath}")
            return jsonify({'error': 'File not found'}), 404
            
        if not os.path.isfile(filepath):
            logger.error(f"Path is not a file: {filepath}")
            return jsonify({'error': 'Not a file'}), 400
            
        # Get the MIME type
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            mime_type = 'application/octet-stream'
            
        return send_file(filepath, mimetype=mime_type)
    except Exception as e:
        logger.error(f"Error serving file {filepath}: {str(e)}")
        return jsonify({'error': str(e)}), 500

def calculate_file_hash(file_path):
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def find_duplicate_files(directory):
    """Find duplicate files in the given directory."""
    hash_dict = {}
    duplicates = []
    
    try:
        for root, _, filenames in os.walk(directory):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                if os.path.isfile(file_path):
                    file_hash = calculate_file_hash(file_path)
                    if file_hash in hash_dict:
                        # Found a duplicate
                        original_file = hash_dict[file_hash]
                        duplicates.append({
                            'original': {
                                'path': original_file,
                                'name': os.path.basename(original_file),
                                'size': os.path.getsize(original_file),
                                'modified': datetime.fromtimestamp(os.path.getmtime(original_file)).strftime('%Y-%m-%d %H:%M:%S')
                            },
                            'duplicate': {
                                'path': file_path,
                                'name': filename,
                                'size': os.path.getsize(file_path),
                                'modified': datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')
                            },
                            'hash': file_hash
                        })
                    else:
                        hash_dict[file_hash] = file_path
    except Exception as e:
        logger.error(f"Error finding duplicate files: {str(e)}")
        raise
    
    return duplicates

@app.route('/api/duplicates', methods=['POST'])
def find_duplicates():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        directory = data.get('directory')
        if not directory:
            return jsonify({'error': 'No directory provided'}), 400
            
        # Normalize the directory path
        directory = os.path.normpath(directory)
        logger.info(f"Searching for duplicates in directory: {directory}")
        
        if not os.path.exists(directory):
            logger.error(f"Directory does not exist: {directory}")
            return jsonify({'error': f'Directory does not exist: {directory}'}), 404
            
        if not os.path.isdir(directory):
            logger.error(f"Path is not a directory: {directory}")
            return jsonify({'error': f'Path is not a directory: {directory}'}), 400
            
        duplicates = find_duplicate_files(directory)
        return jsonify({'duplicates': duplicates})
    except Exception as e:
        logger.error(f"Error finding duplicates: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete-duplicate', methods=['POST'])
def delete_duplicate():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        file_path = data.get('file_path')
        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400
            
        # Normalize the file path
        file_path = os.path.normpath(file_path)
        logger.info(f"Attempting to delete file: {file_path}")
        
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return jsonify({'error': 'File not found'}), 404
            
        if not os.path.isfile(file_path):
            logger.error(f"Path is not a file: {file_path}")
            return jsonify({'error': 'Not a file'}), 400
            
        # Move file to recycle bin instead of permanent deletion
        os.remove(file_path)
        logger.info(f"Successfully deleted file: {file_path}")
        
        return jsonify({'message': 'File deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 
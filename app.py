from flask import Flask, render_template, request, send_file, redirect, url_for
import os
from validator import validate_emails_from_csv
import time
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            start_time = time.time()
            
            # Process the file with your validation logic
            output_filename = f"validated_{filename}"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
            
            stats = validate_emails_from_csv(filepath, output_path)
            
            processing_time = round(time.time() - start_time, 2)
            
            return render_template('results.html', 
                                 filename=output_filename,
                                 stats=stats,
                                 processing_time=processing_time)
    
    return render_template('index.html')

@app.route('/download/<filename>')
def download(filename):
    return send_file(
        os.path.join(app.config['UPLOAD_FOLDER'], filename),
        as_attachment=True,
        download_name=filename
    )

if __name__ == '__main__':
    app.run(debug=True)
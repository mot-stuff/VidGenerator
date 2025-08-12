// TTS Shorts Generator JavaScript

// Global state
let selectedVideos = {video1: null, video2: null};
let splitScreenEnabled = false;
let youtubeEnabled = false;
let autoUploadEnabled = false;
let batchMode = false;
let csvTexts = [];

// Initialize the app
document.addEventListener('DOMContentLoaded', function() {
    updateStatus();
    refreshFileList();
    setInterval(updateStatus, 2000);
});

function updateStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(data => {
            document.getElementById('statusText').textContent = data.status;
            youtubeEnabled = data.youtube_enabled;
            autoUploadEnabled = data.auto_upload_enabled;
            updateYoutubeButton();
        })
        .catch(e => console.error('Error:', e));
}

function toggleSplitScreen() {
    splitScreenEnabled = document.getElementById('splitScreen').checked;
    const video2Section = document.getElementById('video2Section');
    const video1Label = document.getElementById('video1Label');
    
    if (splitScreenEnabled) {
        video2Section.classList.add('show');
        video1Label.textContent = '(Top Half)';
    } else {
        video2Section.classList.remove('show');
        video1Label.textContent = '';
        // Clear second video when disabling split screen
        selectedVideos.video2 = null;
        const video2Info = document.getElementById('video2Info');
        if (video2Info) {
            video2Info.classList.add('hidden');
        }
        // Clear the file input
        const video2Input = document.getElementById('video2');
        if (video2Input) {
            video2Input.value = '';
        }
    }
    
    fetch('/api/toggle_split_screen', {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: splitScreenEnabled})
    });
}

function uploadVideo(videoType) {
    console.log('Uploading video type:', videoType);
    const input = document.getElementById(videoType);
    if (!input) {
        console.error('Input element not found for:', videoType);
        return;
    }
    
    const file = input.files[0];
    if (!file) {
        console.log('No file selected for:', videoType);
        return;
    }
    console.log('File selected:', file.name, 'for type:', videoType);
    
    const formData = new FormData();
    formData.append('video', file);
    formData.append('type', videoType);
    
    fetch('/api/upload_video', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            console.log('Upload response for', videoType, ':', data);
            if (data.success) {
                selectedVideos[videoType] = data.path;
                const info = document.getElementById(videoType + 'Info');
                if (info) {
                    info.textContent = `✅ ${data.filename}`;
                    info.classList.remove('hidden');
                } else {
                    console.error('Info element not found for:', videoType);
                }
            } else { 
                console.error('Upload failed:', data.error);
                alert('Error uploading video: ' + data.error); 
            }
        })
        .catch(e => { 
            console.error('Upload error for', videoType, ':', e); 
            alert('Error uploading video: ' + e.message); 
        });
}

function toggleBatchMode() {
    batchMode = document.getElementById('batchMode').checked;
    const singleSection = document.getElementById('singleTextSection');
    const batchSection = document.getElementById('batchSection');
    
    if (batchMode) {
        singleSection.classList.add('hidden');
        batchSection.classList.remove('hidden');
    } else {
        singleSection.classList.remove('hidden');
        batchSection.classList.add('hidden');
        csvTexts = [];
        document.getElementById('batchGenerateBtn').disabled = true;
    }
}

function uploadCSV() {
    const input = document.getElementById('csvFile');
    const file = input.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('csv', file);
    
    fetch('/api/upload_csv', { method: 'POST', body: formData })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                csvTexts = data.texts;
                const info = document.getElementById('csvInfo');
                info.textContent = `✅ ${data.count} text entries loaded`;
                info.classList.remove('hidden');
                document.getElementById('batchGenerateBtn').disabled = false;
            } else {
                alert('Error loading CSV: ' + data.error);
            }
        })
        .catch(e => {
            console.error('Error:', e);
            alert('Error uploading CSV');
        });
}

function generateVideo() {
    const text = document.getElementById('textInput').value.trim();
    if (!text) { 
        alert('Please enter some text'); 
        return; 
    }
    if (!selectedVideos.video1) { 
        alert('Please select at least one video'); 
        return; 
    }
    if (splitScreenEnabled && !selectedVideos.video2) { 
        alert('Please select both videos for split screen mode'); 
        return; 
    }
    
    fetch('/api/generate_video', {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) { 
            setTimeout(refreshFileList, 5000); 
        } else { 
            alert('Error: ' + data.error); 
        }
    })
    .catch(e => { 
        console.error('Error:', e); 
        alert('Error generating video'); 
    });
}

function generateBatchVideos() {
    if (csvTexts.length === 0) { 
        alert('Please upload a CSV file first'); 
        return; 
    }
    if (!selectedVideos.video1) { 
        alert('Please select at least one video'); 
        return; 
    }
    if (splitScreenEnabled && !selectedVideos.video2) { 
        alert('Please select both videos for split screen mode'); 
        return; 
    }
    
    fetch('/api/generate_batch', {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({texts: csvTexts})
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) { 
            setTimeout(refreshFileList, 10000); 
        } else { 
            alert('Error: ' + data.error); 
        }
    })
    .catch(e => { 
        console.error('Error:', e); 
        alert('Error generating batch videos'); 
    });
}

function toggleYoutube() {
    fetch('/api/youtube/toggle', { 
        method: 'POST', 
        headers: {'Content-Type': 'application/json'}, 
        body: JSON.stringify({}) 
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            youtubeEnabled = data.enabled || youtubeEnabled;
            autoUploadEnabled = data.auto_upload || false;
            updateYoutubeButton();
        } else { 
            alert('Error: ' + data.error); 
        }
    })
    .catch(e => { 
        console.error('Error:', e); 
        alert('Error with YouTube setup'); 
    });
}

function updateYoutubeButton() {
    const btn = document.getElementById('youtubeBtn');
    if (!youtubeEnabled) { 
        btn.textContent = '📤 Setup YT'; 
        btn.className = 'btn btn-danger'; 
    } else if (!autoUploadEnabled) { 
        btn.textContent = '🔄 Auto Upload'; 
        btn.className = 'btn btn-success'; 
    } else { 
        btn.textContent = '⏸️ Disable Auto'; 
        btn.className = 'btn btn-secondary'; 
    }
}

function cleanup() {
    fetch('/api/cleanup', {method: 'POST'})
        .then(r => r.json())
        .then(data => {
            if (data.success) { 
                document.getElementById('statusText').textContent = '🧹 Cleanup completed'; 
            } else { 
                alert('Cleanup failed: ' + data.error); 
            }
        })
        .catch(e => console.error('Error:', e));
}

function refreshFileList() {
    fetch('/api/export_files')
        .then(r => r.json())
        .then(data => {
            const fileList = document.getElementById('fileList');
            if (data.files && data.files.length > 0) {
                fileList.innerHTML = data.files.map(file => `
                    <div class="file-item">
                        <div><strong>${file.name}</strong><br>
                        <small>${formatFileSize(file.size)} • ${formatDate(file.created)}</small></div>
                        <a href="/export/${file.name}" download class="btn" style="margin: 0;">📥 Download</a>
                    </div>`).join('');
            } else {
                fileList.innerHTML = '<div style="padding: 20px; text-align: center; color: #6b7280;">No videos generated yet</div>';
            }
        })
        .catch(e => console.error('Error:', e));
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024; 
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDate(timestamp) { 
    return new Date(timestamp * 1000).toLocaleString(); 
}

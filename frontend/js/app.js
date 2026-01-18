// MeetBrief 前端應用

const API_BASE = '/api/meetings';

// 狀態
let meetings = [];
let currentMeeting = null;
let isEditing = false;
let refreshInterval = null;

// DOM 元素
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const uploadProgress = document.getElementById('upload-progress');
const progressBar = document.getElementById('progress-bar');
const progressText = document.getElementById('progress-text');
const meetingsList = document.getElementById('meetings-list');
const emptyState = document.getElementById('empty-state');
const meetingModal = document.getElementById('meeting-modal');
const modalTitle = document.getElementById('modal-title');
const modalInfo = document.getElementById('modal-info');
const closeModal = document.getElementById('close-modal');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initUpload();
    initModal();
    loadMeetings();
    startAutoRefresh();
});

// ===== 上傳功能 =====

function initUpload() {
    // 點擊上傳
    uploadArea.addEventListener('click', () => fileInput.click());

    // 檔案選擇
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadFile(e.target.files[0]);
        }
    });

    // 拖曳上傳
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            uploadFile(e.dataTransfer.files[0]);
        }
    });
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    uploadProgress.classList.remove('hidden');
    progressBar.style.width = '0%';
    progressText.textContent = '上傳中...';

    try {
        const xhr = new XMLHttpRequest();

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percent = (e.loaded / e.total) * 100;
                progressBar.style.width = `${percent}%`;
                progressText.textContent = `上傳中... ${Math.round(percent)}%`;
            }
        };

        xhr.onload = () => {
            if (xhr.status === 200) {
                const meeting = JSON.parse(xhr.responseText);
                progressText.textContent = '上傳完成！開始處理...';
                setTimeout(() => {
                    uploadProgress.classList.add('hidden');
                    loadMeetings();
                }, 1000);
            } else {
                const error = JSON.parse(xhr.responseText);
                progressText.textContent = `上傳失敗: ${error.detail || '未知錯誤'}`;
                progressBar.classList.add('error');
            }
        };

        xhr.onerror = () => {
            progressText.textContent = '上傳失敗: 網路錯誤';
            progressBar.classList.add('error');
        };

        xhr.open('POST', `${API_BASE}/upload`);
        xhr.send(formData);

    } catch (error) {
        console.error('上傳錯誤:', error);
        progressText.textContent = `上傳失敗: ${error.message}`;
    }
}

// ===== 會議列表 =====

async function loadMeetings() {
    try {
        const response = await fetch(API_BASE);
        meetings = await response.json();
        renderMeetings();
    } catch (error) {
        console.error('載入會議列表失敗:', error);
    }
}

function renderMeetings() {
    if (meetings.length === 0) {
        meetingsList.innerHTML = '';
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');
    meetingsList.innerHTML = meetings.map(meeting => `
        <div class="meeting-card" onclick="openMeeting(${meeting.id})">
            <div class="card-content">
                <div class="card-info">
                    <h3>${escapeHtml(meeting.title)}</h3>
                    <p>${meeting.filename} · ${formatDuration(meeting.duration)}${meeting.language ? ` · ${meeting.language.toUpperCase()}` : ''}</p>
                    <p class="card-date">${formatDate(meeting.created_at)}</p>
                </div>
                <div class="card-actions">
                    <span class="status-badge status-${meeting.status}">${getStatusText(meeting.status)}</span>
                    <button class="delete-btn" onclick="event.stopPropagation(); deleteMeeting(${meeting.id})">
                        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                        </svg>
                    </button>
                </div>
            </div>
            ${meeting.error_message ? `<p class="card-error">${escapeHtml(meeting.error_message)}</p>` : ''}
        </div>
    `).join('');
}

function getStatusText(status) {
    const statusMap = {
        'pending': '等待處理',
        'transcribing': '轉錄中',
        'summarizing': '生成摘要',
        'completed': '完成',
        'error': '錯誤'
    };
    return statusMap[status] || status;
}

async function deleteMeeting(id) {
    if (!confirm('確定要刪除此會議記錄嗎？')) return;

    try {
        await fetch(`${API_BASE}/${id}`, { method: 'DELETE' });
        loadMeetings();
    } catch (error) {
        console.error('刪除失敗:', error);
        alert('刪除失敗');
    }
}

// ===== Modal =====

function initModal() {
    closeModal.addEventListener('click', closeMeetingModal);
    meetingModal.addEventListener('click', (e) => {
        if (e.target === meetingModal) closeMeetingModal();
    });

    // 標籤頁切換
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // 編輯按鈕
    document.getElementById('edit-transcript-btn').addEventListener('click', startEditTranscript);
    document.getElementById('save-transcript-btn').addEventListener('click', saveTranscript);
    document.getElementById('cancel-edit-btn').addEventListener('click', cancelEditTranscript);

    // 摘要按鈕
    document.getElementById('generate-summary-btn').addEventListener('click', generateSummary);

    // 匯出按鈕
    document.getElementById('export-md-btn').addEventListener('click', () => exportMeeting('markdown'));
    document.getElementById('export-txt-btn').addEventListener('click', () => exportMeeting('txt'));

    // 重新轉錄按鈕
    document.getElementById('retranscribe-btn').addEventListener('click', retranscribe);
}

async function openMeeting(id) {
    try {
        const response = await fetch(`${API_BASE}/${id}`);
        currentMeeting = await response.json();
        renderModal();
        meetingModal.classList.remove('hidden');
        meetingModal.classList.add('show');
    } catch (error) {
        console.error('載入會議失敗:', error);
        alert('載入會議失敗');
    }
}

function closeMeetingModal() {
    meetingModal.classList.remove('show');
    meetingModal.classList.add('hidden');
    currentMeeting = null;
    isEditing = false;
}

function renderModal() {
    if (!currentMeeting) return;

    modalTitle.textContent = currentMeeting.title;
    modalInfo.innerHTML = `
        <p><strong>檔案:</strong> ${escapeHtml(currentMeeting.filename)}</p>
        <p><strong>長度:</strong> ${formatDuration(currentMeeting.duration)}</p>
        <p><strong>語言:</strong> ${currentMeeting.language?.toUpperCase() || '未偵測'}</p>
        <p><strong>狀態:</strong> <span class="status-badge status-${currentMeeting.status}">${getStatusText(currentMeeting.status)}</span></p>
    `;

    renderSummaryTab();
    renderTranscriptTab();
    switchTab('summary');
}

function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('hidden', content.id !== `tab-${tab}`);
    });
}

function renderSummaryTab() {
    const content = document.getElementById('summary-content');
    const loading = document.getElementById('summary-loading');
    const empty = document.getElementById('summary-empty');

    if (currentMeeting.status === 'summarizing') {
        content.classList.add('hidden');
        loading.classList.remove('hidden');
        empty.classList.add('hidden');
    } else if (currentMeeting.summary) {
        content.innerHTML = renderMarkdown(currentMeeting.summary);
        content.classList.remove('hidden');
        loading.classList.add('hidden');
        empty.classList.add('hidden');
    } else {
        content.classList.add('hidden');
        loading.classList.add('hidden');
        empty.classList.remove('hidden');
    }
}

function renderTranscriptTab() {
    const view = document.getElementById('transcript-view');
    const edit = document.getElementById('transcript-edit');
    const loading = document.getElementById('transcript-loading');
    const empty = document.getElementById('transcript-empty');

    if (currentMeeting.status === 'transcribing') {
        view.classList.add('hidden');
        edit.classList.add('hidden');
        loading.classList.remove('hidden');
        empty.classList.add('hidden');
    } else if (currentMeeting.transcript) {
        view.textContent = currentMeeting.transcript;
        view.classList.remove('hidden');
        edit.classList.add('hidden');
        loading.classList.add('hidden');
        empty.classList.add('hidden');
    } else {
        view.classList.add('hidden');
        edit.classList.add('hidden');
        loading.classList.add('hidden');
        empty.classList.remove('hidden');
    }
}

// ===== 編輯功能 =====

function startEditTranscript() {
    isEditing = true;
    const view = document.getElementById('transcript-view');
    const edit = document.getElementById('transcript-edit');

    edit.value = currentMeeting.transcript || '';
    view.classList.add('hidden');
    edit.classList.remove('hidden');

    document.getElementById('edit-transcript-btn').classList.add('hidden');
    document.getElementById('save-transcript-btn').classList.remove('hidden');
    document.getElementById('cancel-edit-btn').classList.remove('hidden');
}

async function saveTranscript() {
    const edit = document.getElementById('transcript-edit');
    const newTranscript = edit.value;

    try {
        const response = await fetch(`${API_BASE}/${currentMeeting.id}/transcript`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: newTranscript })
        });

        if (response.ok) {
            currentMeeting.transcript = newTranscript;
            cancelEditTranscript();
            renderTranscriptTab();
        } else {
            alert('儲存失敗');
        }
    } catch (error) {
        console.error('儲存失敗:', error);
        alert('儲存失敗');
    }
}

function cancelEditTranscript() {
    isEditing = false;
    const view = document.getElementById('transcript-view');
    const edit = document.getElementById('transcript-edit');

    view.classList.remove('hidden');
    edit.classList.add('hidden');

    document.getElementById('edit-transcript-btn').classList.remove('hidden');
    document.getElementById('save-transcript-btn').classList.add('hidden');
    document.getElementById('cancel-edit-btn').classList.add('hidden');
}

// ===== 摘要功能 =====

async function generateSummary() {
    if (!currentMeeting.transcript) {
        alert('請先等待轉錄完成');
        return;
    }

    const content = document.getElementById('summary-content');
    const loading = document.getElementById('summary-loading');
    const empty = document.getElementById('summary-empty');

    content.classList.add('hidden');
    loading.classList.remove('hidden');
    empty.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/${currentMeeting.id}/summarize`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            currentMeeting.summary = data.summary;
            renderSummaryTab();
        } else {
            const error = await response.json();
            alert(`摘要生成失敗: ${error.detail}`);
            loading.classList.add('hidden');
            empty.classList.remove('hidden');
        }
    } catch (error) {
        console.error('摘要生成失敗:', error);
        alert('摘要生成失敗');
        loading.classList.add('hidden');
        empty.classList.remove('hidden');
    }
}

// ===== 匯出功能 =====

function exportMeeting(format) {
    if (!currentMeeting) return;
    window.location.href = `${API_BASE}/${currentMeeting.id}/export?format=${format}`;
}

// ===== 重新轉錄 =====

async function retranscribe() {
    if (!confirm('確定要重新轉錄嗎？這將覆蓋現有的轉錄文字和摘要。')) return;

    try {
        const response = await fetch(`${API_BASE}/${currentMeeting.id}/transcribe`, {
            method: 'POST'
        });

        if (response.ok) {
            currentMeeting.status = 'pending';
            currentMeeting.transcript = null;
            currentMeeting.summary = null;
            renderModal();
            loadMeetings();
        } else {
            const error = await response.json();
            alert(`重新轉錄失敗: ${error.detail}`);
        }
    } catch (error) {
        console.error('重新轉錄失敗:', error);
        alert('重新轉錄失敗');
    }
}

// ===== 自動刷新 =====

function startAutoRefresh() {
    refreshInterval = setInterval(() => {
        // 如果有正在處理的會議，自動刷新
        const hasProcessing = meetings.some(m =>
            ['pending', 'transcribing', 'summarizing'].includes(m.status)
        );

        if (hasProcessing) {
            loadMeetings();
            // 如果 modal 開啟且當前會議正在處理，也刷新 modal
            if (currentMeeting && ['pending', 'transcribing', 'summarizing'].includes(currentMeeting.status)) {
                openMeeting(currentMeeting.id);
            }
        }
    }, 3000);
}

// ===== 工具函數 =====

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDuration(seconds) {
    if (!seconds) return '未知';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-TW', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function renderMarkdown(text) {
    if (!text) return '';

    // 簡單的 Markdown 渲染
    return text
        // 標題
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        // 粗體
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // 列表
        .replace(/^- \[ \] (.+)$/gm, '<li>☐ $1</li>')
        .replace(/^- \[x\] (.+)$/gm, '<li>☑ $1</li>')
        .replace(/^- (.+)$/gm, '<li>$1</li>')
        .replace(/^(\d+)\. (.+)$/gm, '<li>$1. $2</li>')
        // 段落
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>')
        // 包裝
        .replace(/^/, '<p>')
        .replace(/$/, '</p>')
        // 清理連續的列表項
        .replace(/<\/li><br><li>/g, '</li><li>')
        .replace(/<p><li>/g, '<ul><li>')
        .replace(/<\/li><\/p>/g, '</li></ul>');
}

// 应用状态管理
class AppState {
    constructor() {
        this.currentFile = null;
        this.configValid = false;
        this.processing = false;
        this.connectionTested = false;
        this.init();
    }

    init() {
        this.bindEvents();
        this.clearUploadedFileCache();
        this.checkConfig();
        this.initializeForm();
    }

    // 清除服务器端上传文件缓存
    async clearUploadedFileCache() {
        try {
            const response = await fetch('/api/upload/clear', {
                method: 'DELETE'
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log('清除服务器端缓存:', result.message);
            }
        } catch (error) {
            console.log('清除服务器端缓存失败:', error.message);
        }
    }

    // 初始化表单
    initializeForm() {
        // 设置学习日期为今天
        const today = new Date().toISOString().split('T')[0];
        const learningDateElement = document.getElementById('learning-date');
        if (learningDateElement) {
            learningDateElement.value = today;
        }
        
        // 初始化按钮状态
        this.updateUploadButton();
    }

    // 绑定事件监听器
    bindEvents() {
        // 文件选择事件
        document.getElementById('file-input').addEventListener('change', (e) => {
            this.handleFileSelect(e);
        });
        
        // 上传按钮事件
        document.getElementById('upload-and-sync-btn').addEventListener('click', () => {
            this.uploadAndSync();
        });
        
        // 检查配置按钮事件
        document.getElementById('check-config-btn').addEventListener('click', () => {
            this.checkConfig();
        });
        
        // 关闭服务按钮事件
        document.getElementById('shutdown-btn').addEventListener('click', () => {
            this.shutdownService();
        });
        
        // 下载示例CSV链接事件
        document.getElementById('download-sample-link').addEventListener('click', (e) => {
            e.preventDefault();
            this.downloadSampleCSV();
        });
        
        // 表单字段变化事件
        document.getElementById('course-name').addEventListener('input', () => {
            this.updateFormValidation();
        });
        
        document.getElementById('learning-date').addEventListener('change', () => {
            this.updateFormValidation();
        });
    }

    // 文件选择处理
    handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            // 验证文件类型
            if (!file.name.endsWith('.csv')) {
                this.showError('请选择CSV格式的文件');
                e.target.value = '';
                this.currentFile = null;
                this.updateUploadButton();
                return;
            }

            // 验证文件大小（10MB）
            if (file.size > 10 * 1024 * 1024) {
                this.showError('文件大小超过10MB限制');
                e.target.value = '';
                this.currentFile = null;
                this.updateUploadButton();
                return;
            }

            this.currentFile = file;
            this.displayFileInfo(file);
            this.updateUploadButton();
        } else {
            this.currentFile = null;
            this.hideFileInfo();
            this.updateUploadButton();
        }
    }

    // 显示文件信息
    displayFileInfo(file) {
        const fileInfo = document.getElementById('file-info');
        const fileName = document.getElementById('file-name');
        const fileSize = document.getElementById('file-size');
        
        if (fileName && fileSize) {
            fileName.textContent = file.name;
            fileSize.textContent = this.formatFileSize(file.size);
        }
        
        if (fileInfo) {
            fileInfo.style.display = 'block';
        }
        
        // 更新文件选择标签
        const fileLabel = document.querySelector('.file-select-label .file-text');
        if (fileLabel) {
            fileLabel.textContent = `已选择: ${file.name}`;
        }
    }

    // 隐藏文件信息
    hideFileInfo() {
        const fileInfo = document.getElementById('file-info');
        if (fileInfo) {
            fileInfo.style.display = 'none';
        }
        
        // 重置文件选择标签
        const fileLabel = document.querySelector('.file-select-label .file-text');
        if (fileLabel) {
            fileLabel.textContent = '选择CSV文件';
        }
    }

    // 格式化文件大小
    formatFileSize(bytes) {
        const units = ['B', 'KB', 'MB', 'GB'];
        let size = bytes;
        let unitIndex = 0;
        
        while (size >= 1024 && unitIndex < units.length - 1) {
            size /= 1024;
            unitIndex++;
        }
        
        return `${size.toFixed(1)} ${units[unitIndex]}`;
    }

    // 更新上传按钮状态
    updateUploadButton() {
        const courseNameElement = document.getElementById('course-name');
        const learningDateElement = document.getElementById('learning-date');
        const uploadButton = document.getElementById('upload-and-sync-btn');
        
        // 添加调试信息
        if (!courseNameElement || !learningDateElement || !uploadButton) {
            console.error('找不到必要的DOM元素:', {
                courseNameElement: !!courseNameElement,
                learningDateElement: !!learningDateElement,
                uploadButton: !!uploadButton
            });
            return;
        }
        
        const courseName = courseNameElement.value.trim();
        const learningDate = learningDateElement.value;
        const hasFile = this.currentFile !== null;
        
        // 调试信息
        console.log('表单验证状态:', {
            courseName: courseName,
            learningDate: learningDate,
            hasFile: hasFile,
            configValid: this.configValid,
            courseNameLength: courseName.length,
            learningDateLength: learningDate.length
        });
        
        const isValid = courseName && learningDate && hasFile && this.configValid;
        
        uploadButton.disabled = !isValid;
        
        // 改进验证逻辑，优先显示配置错误
        if (!this.configValid) {
            this.updateProcessStatus('请检查配置', 'error');
        } else if (!courseName) {
            this.updateProcessStatus('请输入课程名称', 'idle');
        } else if (!learningDate) {
            this.updateProcessStatus('请选择学习日期', 'idle');
        } else if (!hasFile) {
            this.updateProcessStatus('请选择CSV文件', 'idle');
        } else {
            this.updateProcessStatus('准备就绪，点击上传按钮开始同步', 'success');
        }
    }

    // 上传并同步
    async uploadAndSync() {
        if (this.processing) return;
        
        const courseNameElement = document.getElementById('course-name');
        const learningDateElement = document.getElementById('learning-date');
        const uploadButton = document.getElementById('upload-and-sync-btn');
        
        const courseName = courseNameElement.value.trim();
        const learningDate = learningDateElement.value;
        
        console.log('开始上传同步，验证状态:', {
            courseName: courseName,
            learningDate: learningDate,
            hasFile: !!this.currentFile,
            configValid: this.configValid,
            processing: this.processing
        });
        
        // 最后验证
        if (!courseName || !learningDate || !this.currentFile) {
            const errorMsg = !courseName ? '请输入课程名称' : 
                            !learningDate ? '请选择学习日期' : '请选择CSV文件';
            console.error('验证失败:', errorMsg);
            this.showError(errorMsg);
            return;
        }
        
        if (!this.configValid) {
            console.error('配置验证失败');
            this.showError('配置验证失败，请检查配置');
            return;
        }
        
        this.processing = true;
        uploadButton.disabled = true;
        uploadButton.textContent = '上传中...';
        
        try {
            // 在上传前先清除服务器端缓存，确保不会使用旧数据
            this.updateProcessStatus('正在清除旧数据...', 'loading');
            await this.clearUploadedFileCache();
            
            // 第一步：上传文件
            this.updateProcessStatus('正在上传文件...', 'loading');
            this.showProgressBar();
            
            const formData = new FormData();
            formData.append('file', this.currentFile);
            formData.append('courseName', courseName);
            formData.append('learningDate', learningDate);
            
            console.log('发送上传请求:', {
                fileName: this.currentFile.name,
                courseName: courseName,
                learningDate: learningDate
            });
            
            const uploadResponse = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            
            console.log('上传响应状态:', uploadResponse.status);
            
            const uploadResult = await uploadResponse.json();
            console.log('上传响应数据:', uploadResult);
            
            if (!uploadResult.success) {
                throw new Error(`文件上传失败: ${uploadResult.message || '未知错误'}`);
            }
            
            // 第二步：开始同步
            this.updateProcessStatus('文件上传成功，正在同步数据...', 'loading');
            
            console.log('开始同步请求...');
            const syncResponse = await fetch('/api/sync', {
                method: 'POST'
            });
            
            console.log('同步响应状态:', syncResponse.status);
            
            const syncResult = await syncResponse.json();
            console.log('同步响应数据:', syncResult);
            
            if (syncResult.success) {
                console.log('同步成功，显示结果');
                this.showSyncSuccess(syncResult);
                // 重置表单
                this.resetForm();
            } else {
                throw new Error(`同步失败: ${syncResult.message || '未知错误'}`);
            }
            
        } catch (error) {
            console.error('上传同步过程出错:', error);
            console.error('错误详情:', {
                message: error.message,
                stack: error.stack
            });
            
            // 显示详细错误信息
            const errorMessage = error.message.includes('NetworkError') || error.message.includes('fetch') 
                ? '网络连接失败，请检查网络或服务器状态' 
                : error.message;
            
            this.showError(errorMessage);
            this.updateProcessStatus(`❌ ${errorMessage}`, 'error');
            
        } finally {
            this.processing = false;
            this.hideProgressBar();
            uploadButton.disabled = false;
            uploadButton.textContent = '📤 上传并开始同步';
            // 重新检查按钮状态
            this.updateUploadButton();
        }
    }

    // 重置表单
    resetForm() {
        document.getElementById('course-name').value = '';
        document.getElementById('learning-date').value = new Date().toISOString().split('T')[0];
        document.getElementById('file-input').value = '';
        this.currentFile = null;
        this.hideFileInfo();
        this.updateUploadButton();
    }

    // 检查配置
    async checkConfig() {
        const statusElement = document.getElementById('config-status');
        statusElement.innerHTML = '<div class="loading">正在检查配置...</div>';
        
        console.log('开始检查配置...');
        
        try {
            // 获取配置信息
            const configResponse = await fetch('/api/config');
            const configResult = await configResponse.json();
            
            console.log('配置获取结果:', configResult);
            
            if (!configResult.success) {
                this.showConfigError('配置未加载');
                this.configValid = false;
                console.log('配置未加载，设置 configValid = false');
                this.updateUploadButton();
                return;
            }
            
            // 验证配置
            const validateResponse = await fetch('/api/config/validate', {
                method: 'POST'
            });
            const validateResult = await validateResponse.json();
            
            console.log('配置验证结果:', validateResult);
            
            if (validateResult.success) {
                this.showConfigSuccess('配置验证成功', validateResult.data);
                this.configValid = true;
                console.log('配置验证成功，设置 configValid = true');
                
                // 显示连接测试按钮
                this.showConnectionTestButton();
            } else {
                this.showConfigError('配置验证失败', validateResult.data);
                this.configValid = false;
                console.log('配置验证失败，设置 configValid = false');
            }
            
            // 更新按钮状态
            console.log('配置检查完成，当前 configValid =', this.configValid);
            this.updateUploadButton();
        } catch (error) {
            console.error('配置检查异常:', error);
            this.showConfigError('配置检查失败: ' + error.message);
            this.configValid = false;
            this.updateUploadButton();
        }
    }

    // 显示连接测试按钮
    showConnectionTestButton() {
        const statusElement = document.getElementById('config-status');
        if (!document.getElementById('test-connection-btn')) {
            const button = document.createElement('button');
            button.id = 'test-connection-btn';
            button.className = 'btn btn-primary';
            button.textContent = '测试飞书连接';
            button.style.marginLeft = '10px';
            button.addEventListener('click', this.testConnection.bind(this));
            
            statusElement.appendChild(button);
        }
    }

    // 测试连接
    async testConnection() {
        const button = document.getElementById('test-connection-btn');
        const originalText = button.textContent;
        
        button.textContent = '测试中...';
        button.disabled = true;
        
        try {
            const response = await fetch('/api/config/test-connection', {
                method: 'POST'
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showConnectionSuccess(result.data);
                this.connectionTested = true;
            } else {
                this.showConnectionError(result.message);
                this.connectionTested = false;
            }
        } catch (error) {
            this.showConnectionError('连接测试失败: ' + error.message);
            this.connectionTested = false;
        } finally {
            button.textContent = originalText;
            button.disabled = false;
        }
    }

    // 显示连接成功
    showConnectionSuccess(data) {
        const statusElement = document.getElementById('config-status');
        
        let html = '<div class="success">✅ 飞书连接测试成功</div>';
        
        if (data.student_table && data.learning_record_table) {
            html += '<div class="connection-details">';
            html += '<h4>📋 表格信息:</h4>';
            
            if (data.student_table.success) {
                html += `<p>• 学员总表: ✅ ${data.student_table.data.field_count}个字段</p>`;
            } else {
                html += `<p>• 学员总表: ❌ ${data.student_table.message}</p>`;
            }
            
            if (data.learning_record_table.success) {
                html += `<p>• 学习记录表: ✅ ${data.learning_record_table.data.field_count}个字段</p>`;
            } else {
                html += `<p>• 学习记录表: ❌ ${data.learning_record_table.message}</p>`;
            }
            
            html += '</div>';
        }
        
        statusElement.innerHTML = html;
        statusElement.className = 'status-card success-highlight';
    }

    // 显示连接错误
    showConnectionError(message) {
        const statusElement = document.getElementById('config-status');
        statusElement.innerHTML = `<div class="error">❌ ${message}</div>`;
        statusElement.className = 'status-card error-highlight';
    }

    // 显示配置成功状态
    showConfigSuccess(message, data) {
        const statusElement = document.getElementById('config-status');
        let html = `<div class="success">✅ ${message}</div>`;
        
        if (data && data.warnings && data.warnings.length > 0) {
            html += '<div class="warnings">';
            html += '<h4>⚠️ 警告:</h4>';
            data.warnings.forEach(warning => {
                html += `<p>• ${warning}</p>`;
            });
            html += '</div>';
        }
        
        statusElement.innerHTML = html;
        statusElement.className = 'status-card success-highlight';
    }

    // 显示配置错误状态
    showConfigError(message, data) {
        const statusElement = document.getElementById('config-status');
        let html = `<div class="error">❌ ${message}</div>`;
        
        if (data && data.errors && data.errors.length > 0) {
            html += '<div class="errors">';
            html += '<h4>错误列表:</h4>';
            data.errors.forEach(error => {
                html += `<p>• ${error}</p>`;
            });
            html += '</div>';
        }
        
        statusElement.innerHTML = html;
        statusElement.className = 'status-card error-highlight';
    }

    // 更新处理状态
    updateProcessStatus(message, type) {
        const statusElement = document.getElementById('process-status');
        statusElement.innerHTML = `<div class="${type}">${message}</div>`;
    }

    // 显示进度条
    showProgressBar() {
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.display = 'block';
        
        // 模拟进度更新
        let progress = 0;
        const interval = setInterval(() => {
            progress += Math.random() * 15;
            if (progress >= 95) {
                progress = 95;
            }
            
            const progressFill = progressBar.querySelector('.progress-fill');
            progressFill.style.width = `${progress}%`;
            
            if (!this.processing) {
                progress = 100;
                progressFill.style.width = '100%';
                clearInterval(interval);
            }
        }, 300);
    }

    // 隐藏进度条
    hideProgressBar() {
        setTimeout(() => {
            const progressBar = document.getElementById('progress-bar');
            progressBar.style.display = 'none';
            
            const progressFill = progressBar.querySelector('.progress-fill');
            progressFill.style.width = '0%';
        }, 1000);
    }

    // 显示同步成功结果
    showSyncSuccess(result) {
        this.updateProcessStatus('✅ 同步完成！', 'success');
        
        const resultSection = document.getElementById('result-section');
        const resultContent = document.getElementById('result-content');
        
        const data = result.data;
        
        let html = '<div class="result-summary">';
        html += '<h3>✅ 同步完成</h3>';
        html += `<p>处理时间: ${data.duration_seconds ? data.duration_seconds.toFixed(1) + '秒' : '未知'}</p>`;
        html += `<p>成功率: ${(data.success_rate * 100).toFixed(1)}%</p>`;
        html += '</div>';
        
        html += '<div class="result-details">';
        
        html += `<div class="result-item">
            <span>总记录数</span>
            <span class="result-value">${data.total_records}</span>
        </div>`;
        
        html += `<div class="result-item">
            <span>处理记录数</span>
            <span class="result-value">${data.processed_records}</span>
        </div>`;
        
        html += `<div class="result-item">
            <span>新增学员</span>
            <span class="result-value">${data.new_students}</span>
        </div>`;
        
        if (data.updated_students > 0) {
            html += `<div class="result-item">
                <span>更新学员</span>
                <span class="result-value">${data.updated_students}</span>
            </div>`;
        }
        
        html += `<div class="result-item">
            <span>新增学习记录</span>
            <span class="result-value">${data.new_learning_records}</span>
        </div>`;
        
        if (data.error_count > 0) {
            html += `<div class="result-item">
                <span>错误数量</span>
                <span class="result-value" style="color: #dc3545;">${data.error_count}</span>
            </div>`;
        }
        
        if (data.conflicts_count > 0) {
            html += `<div class="result-item">
                <span>冲突数量</span>
                <span class="result-value" style="color: #ffc107;">${data.conflicts_count}</span>
            </div>`;
        }
        
        html += '</div>';
        
        // 显示错误详情
        if (data.errors && data.errors.length > 0) {
            html += '<div class="result-errors">';
            html += '<h4>❌ 错误详情:</h4>';
            html += '<ul>';
            data.errors.forEach(error => {
                html += `<li>${error}</li>`;
            });
            html += '</ul>';
            html += '</div>';
        }
        
        // 显示冲突详情（改为可选择的复选框列表）
        if (data.field_mapping && data.field_mapping.conflicts && data.field_mapping.conflicts.length > 0) {
            html += '<div class="result-conflicts">';
            html += '<h4>⚠️ 字段冲突详情:</h4>';
            html += '<p>以下字段存在冲突，请选择要更新为新值的字段：</p>';
            html += '<div class="conflicts-list">';
            
            data.field_mapping.conflicts.forEach((conflict, index) => {
                const conflictId = `conflict_${index}`;
                html += `<div class="conflict-item">
                    <label class="conflict-label">
                        <input type="checkbox" id="${conflictId}" class="conflict-checkbox" 
                               data-user-id="${conflict.user_id}" 
                               data-field-name="${conflict.field_name}" 
                               data-new-value="${conflict.new_value}"
                               data-existing-value="${conflict.existing_value}">
                        <span class="conflict-info">
                            <strong>用户:</strong> ${conflict.nickname || conflict.user_id} | 
                            <strong>字段:</strong> ${conflict.field_name} | 
                            <strong>现有值:</strong> '${conflict.existing_value}' → 
                            <strong>新值:</strong> '${conflict.new_value}'
                        </span>
                    </label>
                </div>`;
            });
            
            html += '</div>';
            html += '<div class="conflicts-actions">';
            html += '<button id="select-all-conflicts" class="btn btn-secondary">全选</button>';
            html += '<button id="deselect-all-conflicts" class="btn btn-secondary">取消全选</button>';
            html += '<button id="update-conflicts-btn" class="btn btn-primary">更新为新值</button>';
            html += '</div>';
            html += '</div>';
        }
        
        // 显示其他警告
        if (data.warnings && data.warnings.length > 0) {
            html += '<div class="result-warnings">';
            html += '<h4>⚠️ 其他警告:</h4>';
            html += '<ul>';
            data.warnings.forEach(warning => {
                html += `<li>${warning}</li>`;
            });
            html += '</ul>';
            html += '</div>';
        }
        
        resultContent.innerHTML = html;
        resultSection.style.display = 'block';
        resultSection.classList.add('fade-in');
        
        // 绑定冲突处理事件
        this.bindConflictEvents();
    }

    // 绑定冲突处理事件
    bindConflictEvents() {
        // 全选按钮
        const selectAllBtn = document.getElementById('select-all-conflicts');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => {
                const checkboxes = document.querySelectorAll('.conflict-checkbox');
                checkboxes.forEach(checkbox => checkbox.checked = true);
            });
        }
        
        // 取消全选按钮
        const deselectAllBtn = document.getElementById('deselect-all-conflicts');
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => {
                const checkboxes = document.querySelectorAll('.conflict-checkbox');
                checkboxes.forEach(checkbox => checkbox.checked = false);
            });
        }
        
        // 更新冲突按钮
        const updateBtn = document.getElementById('update-conflicts-btn');
        if (updateBtn) {
            updateBtn.addEventListener('click', this.updateSelectedConflicts.bind(this));
        }
    }

    // 更新选中的冲突
    async updateSelectedConflicts() {
        const selectedConflicts = [];
        const checkboxes = document.querySelectorAll('.conflict-checkbox:checked');
        
        checkboxes.forEach(checkbox => {
            selectedConflicts.push({
                user_id: checkbox.dataset.userId,
                field_name: checkbox.dataset.fieldName,
                new_value: checkbox.dataset.newValue,
                existing_value: checkbox.dataset.existingValue
            });
        });
        
        if (selectedConflicts.length === 0) {
            alert('请选择要更新的冲突字段');
            return;
        }
        
        try {
            const response = await fetch('/api/conflicts/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    conflicts: selectedConflicts
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 显示成功消息
                const conflictsDiv = document.querySelector('.result-conflicts');
                conflictsDiv.innerHTML = `
                    <div class="success">
                        <h4>✅ 冲突更新完成</h4>
                        <p>成功更新 ${result.data.updated_count} 个字段，失败 ${result.data.failed_count} 个字段</p>
                        ${result.data.errors.length > 0 ? `<p>错误信息: ${result.data.errors.join(', ')}</p>` : ''}
                    </div>
                `;
            } else {
                alert('更新冲突字段失败: ' + result.message);
            }
        } catch (error) {
            console.error('更新冲突字段失败:', error);
            alert('更新冲突字段失败: ' + error.message);
        }
    }

    // 下载示例CSV文件
    async downloadSampleCSV() {
        try {
            const response = await fetch('/api/sample-csv');
            
            if (!response.ok) {
                throw new Error('下载失败');
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'sample_students.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
        } catch (error) {
            console.error('下载示例CSV失败:', error);
            alert('下载示例CSV失败: ' + error.message);
        }
    }

    // 显示错误消息
    showError(message) {
        this.updateProcessStatus(`❌ ${message}`, 'error');
    }

    // 显示成功消息
    showSuccess(message) {
        this.updateProcessStatus(`✅ ${message}`, 'success');
    }

    // 关闭服务
    async shutdownService() {
        // 显示确认对话框
        const confirmShutdown = confirm(
            '确定要关闭服务吗？\n\n' +
            '关闭后您需要重新启动服务才能继续使用。\n' +
            '确保已保存所有重要数据。'
        );
        
        if (!confirmShutdown) {
            return;
        }
        
        try {
            // 更新按钮状态
            const shutdownBtn = document.getElementById('shutdown-btn');
            const originalText = shutdownBtn.innerHTML;
            shutdownBtn.innerHTML = '⏳ 正在关闭...';
            shutdownBtn.disabled = true;
            
            // 发送关闭请求
            const response = await fetch('/api/shutdown', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 显示关闭成功消息
                shutdownBtn.innerHTML = '✅ 服务已关闭';
                
                // 显示关闭提示
                alert('服务器正在关闭，感谢使用！\n\n页面将在几秒钟后失去连接。');
                
                // 延迟后刷新页面或显示断开连接的消息
                setTimeout(() => {
                    document.body.innerHTML = `
                        <div style="
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            text-align: center;
                            font-family: Arial, sans-serif;
                        ">
                            <h1 style="font-size: 3em; margin-bottom: 20px;">🔌 服务已关闭</h1>
                            <p style="font-size: 1.2em; margin-bottom: 30px;">感谢使用 NVC学员信息同步工具！</p>
                            <p style="font-size: 1em; opacity: 0.8;">如需重新使用，请重新启动服务</p>
                            <div style="margin-top: 40px; padding: 20px; background: rgba(255,255,255,0.1); border-radius: 10px;">
                                <p style="margin: 0;">重启命令：</p>
                                <code style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 5px; display: inline-block; margin-top: 10px;">python start.py</code>
                            </div>
                        </div>
                    `;
                }, 2000);
                
            } else {
                // 关闭失败，恢复按钮状态
                shutdownBtn.innerHTML = originalText;
                shutdownBtn.disabled = false;
                alert('关闭服务失败: ' + result.message);
            }
            
        } catch (error) {
            console.error('关闭服务失败:', error);
            
            // 恢复按钮状态
            const shutdownBtn = document.getElementById('shutdown-btn');
            shutdownBtn.innerHTML = '🔌 关闭服务';
            shutdownBtn.disabled = false;
            
            // 如果是网络错误，可能服务已经关闭
            if (error.name === 'TypeError' && error.message.includes('fetch')) {
                alert('服务器连接已断开，服务可能已经关闭。');
                // 显示断开连接的页面
                setTimeout(() => {
                    document.body.innerHTML = `
                        <div style="
                            display: flex;
                            flex-direction: column;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            text-align: center;
                            font-family: Arial, sans-serif;
                        ">
                            <h1 style="font-size: 3em; margin-bottom: 20px;">🔌 连接已断开</h1>
                            <p style="font-size: 1.2em; margin-bottom: 30px;">服务器已关闭或无法连接</p>
                            <p style="font-size: 1em; opacity: 0.8;">如需重新使用，请重新启动服务</p>
                        </div>
                    `;
                }, 1000);
            } else {
                alert('关闭服务失败: ' + error.message);
            }
        }
    }
}

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('页面DOM加载完成，开始初始化应用...');
    
    const app = new AppState();
    
    // 添加一些调试信息
    console.log('NVC学员信息同步工具已加载');
    console.log('Version: 2.1.0 - 简化版本 (调试模式)');
    
    // 3秒后检查一次状态
    setTimeout(() => {
        console.log('3秒后状态检查:', {
            configValid: app.configValid,
            currentFile: app.currentFile,
            processing: app.processing
        });
    }, 3000);
}); 
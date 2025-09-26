# 飞书API集成编程经验总结

## 项目背景

本文档总结了"素材快捷投递工具"项目中集成飞书多维表格API的完整编程经验，包括认证机制、文件上传、数据提交等核心功能的实现细节和踩坑经验。

## 核心架构设计

### 1. API客户端类设计

```javascript
class FeishuAPIClient {
  constructor(config) {
    this.config = config || {};
    this.accessToken = null;
    this.tokenExpireTime = 0;
  }

  updateConfig(config) {
    this.config = { ...this.config, ...config };
    // 配置更新时清除现有token，强制重新获取
    this.accessToken = null;
    this.tokenExpireTime = 0;
  }
}
```

**设计亮点：**
- 单例模式管理token，避免频繁请求
- 配置热更新支持
- 内存缓存token和过期时间

## 认证机制实现

### 1. 核心认证代码

```javascript
async getAccessToken() {
  if (!this.config.feishuAppId || !this.config.feishuAppSecret) {
    console.error('Missing credentials:', {
      hasAppId: !!this.config.feishuAppId,
      hasAppSecret: !!this.config.feishuAppSecret
    });
    throw new Error('Missing Feishu App ID or App Secret');
  }

  // 检查token是否还有效（提前5分钟刷新）
  if (this.accessToken && Date.now() < this.tokenExpireTime - 300000) {
    console.log('Using cached token, expires in:', Math.round((this.tokenExpireTime - Date.now()) / 1000), 'seconds');
    return this.accessToken;
  }

  console.log('Requesting new access token...');
  try {
    const response = await fetch('https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8'
      },
      body: JSON.stringify({
        app_id: this.config.feishuAppId,
        app_secret: this.config.feishuAppSecret
      })
    });

    console.log('Token request status:', response.status);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('Token request failed:', {
        status: response.status,
        statusText: response.statusText,
        error: errorText
      });
      throw new Error(`Failed to get access token: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    console.log('Token response:', {
      code: data.code,
      msg: data.msg,
      hasToken: !!data.app_access_token,
      expire: data.expire
    });
    
    if (data.code !== 0) {
      console.error('API error response:', data);
      throw new Error(`Feishu API error: ${data.msg} (code: ${data.code})`);
    }

    this.accessToken = data.app_access_token;
    this.tokenExpireTime = Date.now() + (data.expire * 1000);
    
    console.log('New token acquired, expires in:', Math.round(data.expire), 'seconds');
    return this.accessToken;
  } catch (error) {
    console.error('Get access token failed:', {
      error: error.message,
      stack: error.stack
    });
    throw error;
  }
}
```

### 2. 认证经验总结

#### 关键要点：
1. **Token缓存机制**：避免频繁请求，提前5分钟刷新
2. **详细错误日志**：记录请求状态、响应码、错误信息
3. **安全性考虑**：敏感信息不完整打印，只显示是否存在
4. **异常处理**：完整的try-catch和错误信息传递

#### 常见问题：
- **App ID/Secret错误**：确保从飞书开发者后台正确获取
- **网络问题**：添加重试机制和超时处理
- **Token过期**：实现自动刷新机制

## 文件上传实现

### 1. 核心上传代码

```javascript
async uploadImage(imageBuffer, fileName, appToken, tableId) {
  try {
    const token = await this.getAccessToken();
    
    // 使用正确的飞书文件上传API
    const formData = new FormData();
    const blob = new Blob([imageBuffer], { type: 'image/png' });
    formData.append('file', blob, fileName);
    formData.append('file_name', fileName);
    formData.append('parent_type', 'bitable_file');
    formData.append('parent_node', appToken); // 使用表格的app_token作为parent_node
    formData.append('size', imageBuffer.length.toString());

    console.log('Uploading image with params:', {
      fileName,
      size: imageBuffer.length,
      parent_type: 'bitable_file',
      parent_node: appToken
    });

    const response = await fetch('https://open.feishu.cn/open-apis/drive/v1/files/upload_all', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
        // 不要设置 Content-Type，让浏览器自动设置 multipart/form-data 的边界
      },
      body: formData
    });

    console.log('Upload response status:', response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Upload error response:', errorText);
      throw new Error(`Upload failed: ${response.status} - ${errorText}`);
    }

    const result = await response.json();
    console.log('Upload response:', result);

    if (result.code === 0 && result.data) {
      // 返回符合飞书附件字段格式的对象
      return {
        file_token: result.data.file_token,
        name: result.data.name || fileName,
        type: result.data.type || result.data.mime_type || 'image/png',
        size: result.data.size || imageBuffer.length
      };
    } else {
      throw new Error(`Upload failed: ${result.msg || 'Unknown error'}`);
    }
  } catch (error) {
    console.error('Failed to upload image:', error);
    throw error;
  }
}
```

### 2. 文件上传经验总结

#### 关键要点：
1. **FormData使用**：正确构造multipart/form-data格式
2. **Content-Type处理**：让浏览器自动设置边界，不要手动设置
3. **parent_node参数**：使用表格的app_token，不是table_id
4. **返回格式标准化**：统一file_token、name、type、size格式

#### 常见问题：
- **权限错误99991672**：需要在飞书应用后台添加`drive:file:upload`权限
- **parent_node错误**：必须使用app_token，不能用table_id
- **文件大小限制**：注意飞书的文件大小限制（通常20MB）

#### 权限测试代码：
```javascript
async testImageUploadPermission() {
  try {
    // 创建一个很小的测试图片数据
    const testImageBuffer = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==', 'base64');
    
    const result = await this.uploadImage(testImageBuffer, 'test-permission.png', appToken, tableId);
    
    return {
      success: true,
      message: 'Upload permission test successful',
      fileToken: result.file_token
    };
  } catch (error) {
    return { 
      success: false, 
      message: error.message,
      isPermissionError: error.message.includes('99991672') || error.message.includes('drive:file:upload')
    };
  }
}
```

## 数据提交实现

### 1. 核心提交代码

```javascript
async addRecord(appToken, tableId, fields) {
  try {
    const token = await this.getAccessToken();
    
    // 处理附件字段 - 确保附件字段格式正确
    const processedFields = { ...fields };
    
    // 如果有附件字段，需要转换格式
    Object.keys(processedFields).forEach(key => {
      const value = processedFields[key];
      if (value && typeof value === 'object' && value.file_token) {
        // 转换为飞书多维表格附件字段格式
        processedFields[key] = [{
          file_token: value.file_token,
          name: value.name,
          type: value.type,
          size: value.size
        }];
      }
    });

    // 使用正确的API格式 - 直接使用fields，不需要records数组
    const requestBody = {
      fields: processedFields
    };

    console.log('Adding record with body:', JSON.stringify(requestBody, null, 2));

    const response = await fetch(`https://open.feishu.cn/open-apis/bitable/v1/apps/${appToken}/tables/${tableId}/records`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(requestBody)
    });

    console.log('Add record response status:', response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Add record error response:', errorText);
      throw new Error(`Failed to add record: ${response.status} ${errorText}`);
    }

    const result = await response.json();
    console.log('Add record response:', result);
    return result;
  } catch (error) {
    console.error('Error adding record:', error);
    throw error;
  }
}
```

### 2. 高级提交方法

```javascript
// 提交文本内容
async submitText(tableConfig, content, submitter, comment) {
  try {
    const fields = {};
    
    // 添加文本内容字段
    if (tableConfig.fieldMapping.textField) {
      fields[tableConfig.fieldMapping.textField] = content;
    }
    
    // 添加注释字段
    if (tableConfig.fieldMapping.commentField && comment) {
      fields[tableConfig.fieldMapping.commentField] = comment;
    }
    
    // 添加提交人字段
    if (tableConfig.fieldMapping.submitterField && submitter) {
      fields[tableConfig.fieldMapping.submitterField] = submitter;
    }
    
    // 添加时间字段
    if (tableConfig.fieldMapping.timeField) {
      fields[tableConfig.fieldMapping.timeField] = Date.now();
    }

    const result = await this.addRecord(tableConfig.appToken, tableConfig.tableId, fields);
    
    if (result.code === 0) {
      return { success: true, data: result.data };
    } else {
      throw new Error(`Failed to submit text: ${result.msg}`);
    }
  } catch (error) {
    console.error('Submit text failed:', error);
    throw error;
  }
}

// 提交图片内容
async submitImage(tableConfig, imageBuffer, fileName, submitter, comment) {
  try {
    // 先上传图片
    const uploadResult = await this.uploadImage(imageBuffer, fileName, tableConfig.appToken, tableConfig.tableId);
    console.log('Image uploaded:', uploadResult);
    
    // 准备记录字段
    const fields = {};
    
    // 添加图片字段
    if (tableConfig.fieldMapping.imageField) {
      fields[tableConfig.fieldMapping.imageField] = uploadResult;
    }
    
    // 添加其他字段
    if (tableConfig.fieldMapping.commentField && comment) {
      fields[tableConfig.fieldMapping.commentField] = comment;
    }
    
    if (tableConfig.fieldMapping.submitterField && submitter) {
      fields[tableConfig.fieldMapping.submitterField] = submitter;
    }
    
    if (tableConfig.fieldMapping.timeField) {
      fields[tableConfig.fieldMapping.timeField] = Date.now();
    }
    
    const result = await this.addRecord(tableConfig.appToken, tableConfig.tableId, fields);
    
    if (result.code === 0) {
      return { success: true, data: result.data };
    } else {
      throw new Error(`Failed to submit image: ${result.msg}`);
    }
  } catch (error) {
    console.error('Submit image failed:', error);
    throw error;
  }
}
```

### 3. 数据提交经验总结

#### 关键要点：
1. **附件字段格式**：必须转换为数组格式，包含file_token、name、type、size
2. **字段映射**：通过配置映射实现灵活的字段对应
3. **数据类型处理**：时间字段使用时间戳，文本字段直接字符串
4. **分步操作**：图片先上传获取file_token，再创建记录

#### 常见问题：
- **附件字段格式错误**：必须是数组格式，不能直接传对象
- **字段名称错误**：使用field_name（中文字段名）而不是field_id
- **权限问题**：确保应用有`bitable:app`权限

## 表格信息获取

### 1. 获取表格字段

```javascript
async getTableFields(tableConfig) {
  console.log('Getting table fields for:', {
    appToken: tableConfig.appToken,
    tableId: tableConfig.tableId
  });

  if (!tableConfig.appToken || !tableConfig.tableId) {
    throw new Error('Missing app token or table ID');
  }

  try {
    const accessToken = await this.getAccessToken();
    
    const url = `https://open.feishu.cn/open-apis/bitable/v1/apps/${tableConfig.appToken}/tables/${tableConfig.tableId}/fields`;
    
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json; charset=utf-8'
      }
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to get table fields: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    
    if (data.code !== 0) {
      throw new Error(`Feishu API error: ${data.msg} (code: ${data.code})`);
    }

    const fields = data.data.items || [];
    console.log('Retrieved fields:', fields.map(f => ({
      field_id: f.field_id,
      field_name: f.field_name,
      type: f.type
    })));
    return fields;
  } catch (error) {
    console.error('Get table fields failed:', error);
    throw error;
  }
}
```

### 2. 字段类型映射

```javascript
// 飞书字段类型常量
const FEISHU_FIELD_TYPES = {
  TEXT: 1,           // 多行文本
  NUMBER: 2,         // 数字
  SINGLE_SELECT: 3,  // 单选
  MULTI_SELECT: 4,   // 多选
  DATE: 5,           // 日期
  CHECKBOX: 7,       // 复选框
  USER: 11,          // 人员
  PHONE: 13,         // 电话号码
  URL: 15,           // 超链接
  ATTACHMENT: 17,    // 附件
  SINGLE_LINE_TEXT: 1005  // 单行文本
};

// 字段类型判断
function isTextField(type) {
  return type === FEISHU_FIELD_TYPES.TEXT || type === FEISHU_FIELD_TYPES.SINGLE_LINE_TEXT;
}

function isAttachmentField(type) {
  return type === FEISHU_FIELD_TYPES.ATTACHMENT;
}

function isDateField(type) {
  return type === FEISHU_FIELD_TYPES.DATE;
}
```

## 错误处理和日志

### 1. 统一错误处理

```javascript
class APIError extends Error {
  constructor(message, code, details) {
    super(message);
    this.name = 'APIError';
    this.code = code;
    this.details = details;
  }
}

// 统一的API调用包装
async function apiCall(url, options, context = '') {
  try {
    console.log(`[${context}] Requesting: ${url}`);
    const response = await fetch(url, options);
    
    console.log(`[${context}] Response status: ${response.status}`);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`[${context}] Request failed:`, {
        status: response.status,
        statusText: response.statusText,
        error: errorText
      });
      throw new APIError(`${context} failed: ${response.status} - ${errorText}`, response.status, errorText);
    }

    const data = await response.json();
    console.log(`[${context}] Response:`, {
      code: data.code,
      msg: data.msg,
      hasData: !!data.data
    });
    
    if (data.code !== 0) {
      console.error(`[${context}] API error:`, data);
      throw new APIError(`${context} API error: ${data.msg}`, data.code, data);
    }

    return data;
  } catch (error) {
    console.error(`[${context}] Failed:`, {
      error: error.message,
      stack: error.stack
    });
    throw error;
  }
}
```

### 2. 日志最佳实践

```javascript
// 敏感信息脱敏
function sanitizeConfig(config) {
  return {
    hasAppId: !!config.feishuAppId,
    hasAppSecret: !!config.feishuAppSecret,
    appIdLength: config.feishuAppId ? config.feishuAppId.length : 0,
    tableCount: config.tableConfigs ? config.tableConfigs.length : 0
  };
}

// 请求参数日志
function logRequestParams(params, context) {
  console.log(`[${context}] Request params:`, {
    ...params,
    // 敏感信息脱敏
    token: params.token ? `${params.token.substring(0, 10)}...` : 'none'
  });
}
```

## 性能优化

### 1. Token缓存优化

```javascript
class TokenManager {
  constructor() {
    this.token = null;
    this.expireTime = 0;
    this.refreshPromise = null;
  }

  async getToken() {
    // 如果正在刷新，等待刷新完成
    if (this.refreshPromise) {
      return await this.refreshPromise;
    }

    // 检查token是否需要刷新（提前5分钟）
    if (this.token && Date.now() < this.expireTime - 300000) {
      return this.token;
    }

    // 开始刷新token
    this.refreshPromise = this.refreshToken();
    
    try {
      const newToken = await this.refreshPromise;
      this.refreshPromise = null;
      return newToken;
    } catch (error) {
      this.refreshPromise = null;
      throw error;
    }
  }

  async refreshToken() {
    // 实际的token刷新逻辑
    // ...
  }
}
```

### 2. 请求并发控制

```javascript
class RequestQueue {
  constructor(concurrency = 3) {
    this.concurrency = concurrency;
    this.running = [];
    this.queue = [];
  }

  async add(requestFunc) {
    return new Promise((resolve, reject) => {
      this.queue.push({
        requestFunc,
        resolve,
        reject
      });
      this.process();
    });
  }

  async process() {
    if (this.running.length >= this.concurrency || this.queue.length === 0) {
      return;
    }

    const { requestFunc, resolve, reject } = this.queue.shift();
    const promise = requestFunc()
      .then(resolve)
      .catch(reject)
      .finally(() => {
        this.running.splice(this.running.indexOf(promise), 1);
        this.process();
      });

    this.running.push(promise);
  }
}
```

## 实时上传实现

### 1. 剪贴板监听

```javascript
// 实时模式相关变量
let realtimeMode = false;
let clipboardWatcher = null;
let lastClipboardContent = { text: '', image: null };

// 启动剪贴板监听
function startClipboardWatcher() {
  if (clipboardWatcher) return;
  
  clipboardWatcher = setInterval(() => {
    try {
      const currentText = clipboard.readText() || '';
      const currentImage = clipboard.readImage();
      const currentImageData = currentImage.isEmpty() ? null : currentImage.toPNG().toString('base64');
      
      // 检查是否有新的剪贴板内容
      let hasNewContent = false;
      let contentType = null;
      let content = null;
      
      if (currentImageData && currentImageData !== lastClipboardContent.image) {
        hasNewContent = true;
        contentType = 'image';
        content = currentImageData;
        lastClipboardContent.image = currentImageData;
      } else if (currentText && currentText.trim() && currentText !== lastClipboardContent.text) {
        hasNewContent = true;
        contentType = 'text';
        content = currentText.trim();
        lastClipboardContent.text = currentText;
      }
      
      if (hasNewContent) {
        console.log(`检测到新的${contentType === 'image' ? '图片' : '文本'}内容，自动上传中...`);
        handleRealtimeUpload(contentType, content);
      }
    } catch (error) {
      console.error('剪贴板监听出错:', error);
    }
  }, 500); // 每500ms检查一次
}

// 处理实时模式上传
async function handleRealtimeUpload(contentType, content) {
  try {
    if (!apiClient) {
      throw new Error('API客户端未初始化');
    }
    
    const currentTable = getCurrentTableConfig();
    if (!currentTable) {
      throw new Error('未选择表格配置');
    }
    
    const submitter = appConfig.submitterName || '未知用户';
    const comment = `实时模式自动上传 - ${new Date().toLocaleString()}`;
    
    let result;
    if (contentType === 'text') {
      result = await apiClient.submitText(currentTable, content, submitter, comment);
    } else if (contentType === 'image') {
      const imageBuffer = Buffer.from(content, 'base64');
      const fileName = `realtime-${Date.now()}.png`;
      result = await apiClient.submitImage(currentTable, imageBuffer, fileName, submitter, comment);
    }
    
    console.log('实时模式上传结果:', result);
  } catch (error) {
    console.error('实时模式上传失败:', error);
  }
}
```

### 2. 连续按键检测

```javascript
// 连续按键检测
let lastShortcutTime = 0;
let shortcutTimerId = null;

function handleShortcutPress() {
  const currentTime = Date.now();
  
  if (currentTime - lastShortcutTime < 500) {
    // 连续按键，启动实时模式
    if (shortcutTimerId) {
      clearTimeout(shortcutTimerId);
      shortcutTimerId = null;
    }
    
    if (!realtimeMode) {
      startRealtimeMode();
    } else {
      stopRealtimeMode();
    }
  } else {
    // 单次按键，设置定时器
    if (shortcutTimerId) {
      clearTimeout(shortcutTimerId);
    }
    
    shortcutTimerId = setTimeout(() => {
      // 单次按键逻辑
      if (!realtimeMode) {
        showCaptureWindow();
      }
      shortcutTimerId = null;
    }, 500);
  }
  
  lastShortcutTime = currentTime;
}
```

## 配置管理

### 1. 配置结构设计

```javascript
const defaultConfig = {
  feishuAppId: '',
  feishuAppSecret: '',
  submitterName: '',
  shortcuts: {
    smartCapture: 'CommandOrControl+Shift+T'
  },
  tableConfigs: [],
  currentTableIndex: -1,
  lastUsedTable: null
};

// 表格配置结构
const tableConfigSchema = {
  id: 'unique-id',
  name: '表格名称',
  appToken: 'app-token',
  tableId: 'table-id',
  fieldMapping: {
    textField: 'field-id-for-text',
    imageField: 'field-id-for-image',
    commentField: 'field-id-for-comment',
    submitterField: 'field-id-for-submitter',
    timeField: 'field-id-for-time'
  }
};
```

### 2. 配置验证

```javascript
function validateConfig(config) {
  const errors = [];
  
  if (!config.feishuAppId) {
    errors.push('缺少飞书应用ID');
  }
  
  if (!config.feishuAppSecret) {
    errors.push('缺少飞书应用密钥');
  }
  
  if (!config.tableConfigs || config.tableConfigs.length === 0) {
    errors.push('至少需要配置一个表格');
  }
  
  config.tableConfigs.forEach((table, index) => {
    if (!table.appToken) {
      errors.push(`表格${index + 1}缺少应用令牌`);
    }
    
    if (!table.tableId) {
      errors.push(`表格${index + 1}缺少表格ID`);
    }
    
    if (!table.fieldMapping.textField && !table.fieldMapping.imageField) {
      errors.push(`表格${index + 1}至少需要配置文本字段或图片字段`);
    }
  });
  
  return {
    valid: errors.length === 0,
    errors
  };
}
```

## 测试和调试

### 1. 连接测试

```javascript
async testConnection() {
  try {
    const token = await this.getAccessToken();
    return {
      success: true,
      message: 'Connection successful',
      data: {
        hasToken: !!token,
        tokenExpire: new Date(this.tokenExpireTime).toISOString()
      }
    };
  } catch (error) {
    console.error('Test connection failed:', error);
    return {
      success: false,
      message: error.message
    };
  }
}

async testTableConfig(tableConfig) {
  try {
    const fields = await this.getTableFields(tableConfig);
    
    return {
      success: true,
      message: 'Table config is valid',
      data: {
        tableName: tableConfig.name || 'Untitled Table',
        fieldCount: fields.length,
        fields: fields.map(field => ({
          id: field.field_id,
          name: field.field_name,
          type: field.type
        }))
      }
    };
  } catch (error) {
    console.error('Test table config failed:', error);
    return {
      success: false,
      message: error.message
    };
  }
}
```

### 2. 调试工具

```javascript
// 调试模式配置
const DEBUG_MODE = process.env.NODE_ENV === 'development';

function debugLog(context, data) {
  if (DEBUG_MODE) {
    console.log(`[DEBUG:${context}]`, data);
  }
}

// API请求调试
function debugAPICall(url, options, response) {
  if (DEBUG_MODE) {
    console.group(`API Call: ${url}`);
    console.log('Request:', options);
    console.log('Response:', response);
    console.groupEnd();
  }
}
```

## 部署和监控

### 1. 环境配置

```javascript
// 环境变量配置
const config = {
  development: {
    apiTimeout: 30000,
    retryCount: 3,
    logLevel: 'debug'
  },
  production: {
    apiTimeout: 10000,
    retryCount: 2,
    logLevel: 'error'
  }
};

const currentConfig = config[process.env.NODE_ENV] || config.development;
```

### 2. 错误监控

```javascript
// 错误统计
class ErrorMonitor {
  constructor() {
    this.errors = new Map();
  }

  recordError(error, context) {
    const key = `${context}:${error.message}`;
    const count = this.errors.get(key) || 0;
    this.errors.set(key, count + 1);
    
    // 发送错误报告（如果需要）
    if (count > 5) {
      this.sendErrorReport(error, context, count);
    }
  }

  sendErrorReport(error, context, count) {
    console.error(`高频错误报告: ${context}`, {
      error: error.message,
      count,
      stack: error.stack
    });
  }
}
```

## 总结

### 关键成功要素

1. **完善的错误处理**：详细的日志记录和错误信息
2. **Token管理**：自动刷新和缓存机制
3. **数据格式处理**：正确的附件字段格式转换
4. **权限配置**：确保飞书应用权限正确设置
5. **性能优化**：请求缓存和并发控制

### 常见陷阱

1. **附件字段格式**：必须是数组格式，不能是对象
2. **parent_node参数**：使用app_token，不是table_id
3. **Content-Type设置**：FormData上传时不要手动设置
4. **权限问题**：确保所有必要的API权限都已开启
5. **Token过期**：实现自动刷新机制

### 最佳实践

1. **分层设计**：API客户端、业务逻辑、界面层分离
2. **配置管理**：统一的配置结构和验证机制
3. **错误处理**：统一的错误处理和日志记录
4. **测试覆盖**：完整的连接测试和配置验证
5. **性能监控**：请求统计和错误监控

这套经验总结涵盖了飞书API集成的所有核心环节，可以作为后续项目的参考模板。 
/**
 * JP_IA - Sistema de Chat Moderno v4.0
 * Interfaz Avanzada con RAG Híbrido
 */

// ===== CONFIGURACIÓN =====
const CONFIG = {
    API_ENDPOINT: '/chat',
    MAX_MESSAGE_LENGTH: 1000,
    TYPING_DELAY: 1500,
    ANIMATION_DURATION: 300,
    AUTO_SCROLL_THRESHOLD: 100
};

// ===== ESTADO GLOBAL =====
const AppState = {
    currentSessionId: null,
    isTyping: false,
    chatHistory: [],
    currentSpecialist: 'general',
    messageQueue: []
};

// ===== INICIALIZACIÓN =====
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Inicializando JP_IA v4.0...');
    
    AppState.currentSessionId = generateSessionId();
    setupEventListeners();
    initializeInterface();
    
    console.log('✅ JP_IA inicializado correctamente');
});

// ===== CONFIGURACIÓN DE EVENTOS =====
function setupEventListeners() {
    // Input de mensaje (ajustado a HTML existente)
    const messageInput = document.getElementById('messageInput');
    // En el HTML el botón tiene clase "send-btn" y no el id sendButton
    const sendButton = document.querySelector('.send-btn');
    
    if (messageInput) {
        messageInput.addEventListener('keydown', handleKeyDown);
        messageInput.addEventListener('input', handleInputChange);
        messageInput.addEventListener('paste', handlePaste);
    }
    
    if (sendButton) {
        sendButton.addEventListener('click', sendMessage);
    }
    
    // Navegación de especialistas (en el HTML usan .specialist-btn)
    document.querySelectorAll('.specialist-btn').forEach(link => {
        link.addEventListener('click', function() {
            const specialist = this.dataset.specialist;
            if (specialist) switchSpecialist(specialist);
        });
    });
    
    // Toggle móvil
    // Botón y overlay móvil en el HTML tienen clases/IDs distintos
    const mobileToggle = document.querySelector('.mobile-menu-btn');
    const sidebarOverlay = document.getElementById('mobileOverlay');

    if (mobileToggle) {
        // algunas plantillas usan onclick inline, aquí aseguramos behavior adicional
        mobileToggle.addEventListener('click', toggleSidebarSafe);
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', toggleSidebarSafe);
    }
    
    // Auto-scroll al hacer scroll
    // En las plantillas el contenedor de mensajes se llama messagesContainer
    const chatContainer = document.getElementById('messagesContainer') || document.getElementById('chatContainer');
    if (chatContainer) {
        chatContainer.addEventListener('scroll', handleChatScroll);
    }
}

// ===== INICIALIZACIÓN DE INTERFAZ =====
function initializeInterface() {
    // Auto-resize textarea
    autoResizeTextarea();
    
    // Estado inicial del botón
    updateSendButton();
    
    // Inicializar especialista por defecto
    switchSpecialist('general');
    
    // Mostrar mensaje de bienvenida
    showWelcomeMessage();
}

// ===== MANEJO DE ENTRADA =====
function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
    
    if (e.key === 'Escape') {
        clearInput();
    }
}

// --- Funciones expuestas para compatibilidad con el HTML inline ---
// Alias seguro para el manejo de la tecla Enter usado en templates
function handleKeyPress(e) {
    if (!e) return;
    handleKeyDown(e);
}

// Toggle seguro para sidebar/mobile - algunas plantillas llaman toggleMobileMenu()
function toggleSidebarSafe() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (!sidebar || !overlay) return;

    sidebar.classList.toggle('active');
    overlay.classList.toggle('active');
}

// Mantener nombres esperados por templates
window.toggleMobileMenu = toggleSidebarSafe;
window.toggleSidebar = toggleSidebarSafe;
window.handleKeyPress = handleKeyPress;
// Exponer sendMessage globalmente por el onclick inline
window.sendMessage = sendMessage;
window.newChat = newChat;
window.quickQuery = quickQuery;

// ===== FUNCIONES AUXILIARES =====
function newChat() {
    // Limpiar el chat actual
    const chatContainer = document.getElementById('chatContainer');
    if (chatContainer) {
        chatContainer.innerHTML = '';
    }
    
    // Mostrar mensaje de bienvenida
    showWelcomeMessage();
    
    // Limpiar input
    clearInput();
    
    // Reiniciar estado
    AppState.chatHistory = [];
    AppState.currentSessionId = generateSessionId();
    
    console.log('🔄 Nueva conversación iniciada');
}

function quickQuery(query) {
    const input = document.getElementById('messageInput');
    if (input) {
        input.value = query;
        sendMessage();
    }
}

function handleInputChange() {
    autoResizeTextarea();
    updateSendButton();
    
    // Remover mensaje de bienvenida al empezar a escribir
    const welcomeMessage = document.getElementById('welcomeMessage');
    if (welcomeMessage && this.value.trim()) {
        welcomeMessage.style.display = 'none';
    }
}

function handlePaste(e) {
    // Prevenir pegado de contenido muy largo
    setTimeout(() => {
        const input = e.target;
        if (input.value.length > CONFIG.MAX_MESSAGE_LENGTH) {
            input.value = input.value.substring(0, CONFIG.MAX_MESSAGE_LENGTH);
            showToast('Mensaje truncado al límite máximo', 'warning');
        }
        autoResizeTextarea();
        updateSendButton();
    }, 10);
}

// ===== FUNCIONES DE TEXTAREA =====
function autoResizeTextarea() {
    const textarea = document.getElementById('messageInput');
    if (!textarea) return;

    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
}

function updateSendButton() {
    const input = document.getElementById('messageInput');
    // boton en templates: .send-btn
    const button = document.querySelector('.send-btn') || document.getElementById('sendButton');
    
    if (!input || !button) return;
    
    const hasText = input.value.trim().length > 0;
    const withinLimit = input.value.length <= CONFIG.MAX_MESSAGE_LENGTH;
    
    button.disabled = !hasText || !withinLimit || AppState.isTyping;
    
    // Actualizar ícono según estado
    const icon = button.querySelector('i');
    if (icon) {
        if (AppState.isTyping) {
            icon.className = 'fas fa-spinner fa-spin';
        } else {
            icon.className = 'fas fa-paper-plane';
        }
    }
}

function clearInput() {
    const input = document.getElementById('messageInput');
    if (input) {
        input.value = '';
        autoResizeTextarea();
        updateSendButton();
    }
}

// ===== ENVÍO DE MENSAJES =====
async function sendMessage() {
    const input = document.getElementById('messageInput');
    if (!input) return;
    
    const message = input.value.trim();
    if (!message || AppState.isTyping) return;
    
    // Validaciones
    if (message.length > CONFIG.MAX_MESSAGE_LENGTH) {
        showToast('Mensaje demasiado largo', 'error');
        return;
    }
    
    // Limpiar input y actualizar estado
    clearInput();
    AppState.isTyping = true;
    updateSendButton();
    
    // Agregar mensaje del usuario
    addUserMessage(message);
    
    // Mostrar indicador de tipeo
    showTypingIndicator();
    
    try {
        // Enviar solicitud
        const response = await fetch(CONFIG.API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                specialist: AppState.currentSpecialist,
                session_id: AppState.currentSessionId
            })
        });
        
        // Procesar respuesta
        if (response.ok) {
            const data = await response.json();
            hideTypingIndicator();
            
            // Verificar si hay una respuesta exitosa
            if (data.response) {
                addBotMessage(data.response, data.sources || []);
            } else if (data.error) {
                addErrorMessage(data.error);
            } else {
                addErrorMessage('Error desconocido');
            }
        } else {
            hideTypingIndicator();
            
            // Manejar diferentes tipos de error
            if (response.status === 401) {
                // Sesión expirada - redirigir al login
                showToast('Tu sesión ha expirado. Redirigiendo al login...', 'warning');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 2000);
                addErrorMessage('⏰ Sesión expirada. Redirigiendo al login...');
            } else if (response.status === 429) {
                // Rate limit excedido
                addErrorMessage('⚠️ Demasiadas consultas. Por favor, espera un momento antes de continuar.');
            } else if (response.status >= 500) {
                // Error del servidor
                addErrorMessage(`🔧 Error interno del servidor (${response.status}). Intenta de nuevo en unos momentos.`);
            } else {
                // Otros errores
                addErrorMessage(`Error del servidor: ${response.status}`);
            }
        }
        
    } catch (error) {
        console.error('Error enviando mensaje:', error);
        hideTypingIndicator();
        addErrorMessage('Error de conexión. Verifique su internet.');
    } finally {
        AppState.isTyping = false;
        updateSendButton();
    }
}

// ===== MANEJO DE MENSAJES EN UI =====
function addUserMessage(text) {
    const messageId = `msg-${Date.now()}-user`;
    
    const messageHtml = `
        <div class="message message-user" id="${messageId}">
            <div class="message-content">
                <div class="message-text">${escapeHtml(text)}</div>
            </div>
        </div>
    `;
    
    appendMessage(messageHtml);
    scrollToBottom();
    
    // Guardar en historial
    AppState.chatHistory.push({
        type: 'user',
        text: text,
        timestamp: new Date().toISOString()
    });
}

function addBotMessage(text, sources = []) {
    const messageId = `msg-${Date.now()}-bot`;
    
    // Procesar texto para formato markdown básico
    const formattedText = formatBotResponse(text);
    
    // Crear HTML de citas si existen
    let citationsHtml = '';
    if (sources && sources.length > 0) {
        citationsHtml = `
            <div class="message-sources">
                <div class="sources-header">
                    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z" fill="currentColor"/>
                    </svg>
                    Fuentes consultadas
                </div>
                <div class="sources-list">
                    ${sources.map(source => `<span class="source-item">${escapeHtml(source)}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    const messageHtml = `
        <div class="message message-bot" id="${messageId}">
            <div class="assistant-avatar-small">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9V7L15 1H5C3.89 1 3 1.89 3 3V19A2 2 0 0 0 5 21H19A2 2 0 0 0 21 19V9M19 9H14V4L19 9Z" fill="currentColor"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-text">${formattedText}</div>
                ${citationsHtml}
            </div>
        </div>
    `;
    
    appendMessage(messageHtml);
    scrollToBottom();
    
    // Guardar en historial
    AppState.chatHistory.push({
        type: 'bot',
        text: text,
        sources: sources,
        timestamp: new Date().toISOString()
    });
}

function addErrorMessage(errorText) {
    const messageId = `msg-${Date.now()}-error`;
    
    const messageHtml = `
        <div class="message message-bot" id="${messageId}">
            <div class="assistant-avatar-small" style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 9V13M12 17H12.01M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-text">
                    <div class="error-message">
                        <strong>Ha ocurrido un error</strong>
                        <p>${escapeHtml(errorText)}</p>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    appendMessage(messageHtml);
    scrollToBottom();
    
    showToast('Error en la respuesta', 'error');
}

function appendMessage(messageHtml) {
    const chatContainer = document.getElementById('chatContainer');
    if (!chatContainer) return;
    
    // Remover mensaje de bienvenida si existe
    const welcomeMessage = document.getElementById('welcomeMessage');
    if (welcomeMessage) {
        welcomeMessage.style.display = 'none';
    }
    
    chatContainer.insertAdjacentHTML('beforeend', messageHtml);
}

// ===== INDICADOR DE TIPEO =====
function showTypingIndicator() {
    // Usar el indicador del área de input si existe
    const inlineTyping = document.getElementById('typingIndicator');
    if (inlineTyping) {
        inlineTyping.classList.add('active');
        inlineTyping.style.display = 'flex';
        return;
    }

    // Fallback: crear indicador en el chat
    const typingId = 'typing-indicator-chat';
    const existing = document.getElementById(typingId);
    if (existing) existing.remove();

    const typingHtml = `
        <div class="message message-bot" id="${typingId}">
            <div class="assistant-avatar-small">
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9V7L15 1H5C3.89 1 3 1.89 3 3V19A2 2 0 0 0 5 21H19A2 2 0 0 0 21 19V9M19 9H14V4L19 9Z" fill="currentColor"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="typing-animation">
                    <div class="typing-dots">
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                        <div class="typing-dot"></div>
                    </div>
                    <span class="typing-text">JP_IA está escribiendo...</span>
                </div>
            </div>
        </div>
    `;
    
    appendMessage(typingHtml);
    scrollToBottom();
}

function hideTypingIndicator() {
    // Ocultar indicador del área de input
    const inlineTyping = document.getElementById('typingIndicator');
    if (inlineTyping) {
        inlineTyping.classList.remove('active');
        inlineTyping.style.display = 'none';
    }
    
    // Remover indicador del chat si existe
    const chatTyping = document.getElementById('typing-indicator-chat');
    if (chatTyping) {
        chatTyping.remove();
    }
    
    AppState.isTyping = false;
    updateSendButton();
}

function appendMessage(messageHtml) {
    const chatContainer = document.getElementById('chatContainer');
    if (!chatContainer) return;
    
    // Remover mensaje de bienvenida si existe
    const welcomeMessage = document.getElementById('welcomeMessage');
    if (welcomeMessage) {
        welcomeMessage.style.display = 'none';
    }
    
    chatContainer.insertAdjacentHTML('beforeend', messageHtml);
}

// ===== NAVEGACIÓN DE ESPECIALISTAS =====
function switchSpecialist(specialistId) {
    AppState.currentSpecialist = specialistId;
    
    // Actualizar UI de navegación
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.toggle('active', link.dataset.specialist === specialistId);
    });
    
    // Actualizar header
    updateSpecialistHeader(specialistId);
    
    // Limpiar chat y mostrar bienvenida
    clearChat();
    showWelcomeMessage();
}

function updateSpecialistHeader(specialistId) {
    const specialists = {
        general: {
            title: 'Chat General',
            subtitle: 'Análisis completo de todos los Reglamentos de Planificación',
            icon: 'fas fa-comments'
        },
        procedimientos: {
            title: 'Procedimientos',
            subtitle: 'Trámites administrativos y más',
            icon: 'fas fa-clipboard-list'
        },
        tecnico: {
            title: 'Técnico Gráfico',
            subtitle: 'Planos, mapas y documentos técnicos',
            icon: 'fas fa-drafting-compass'
        },
        edificabilidad: {
            title: 'Edificabilidad',
            subtitle: 'Construcción y densidad urbana',
            icon: 'fas fa-building'
        },
        zonificacion: {
            title: 'Zonificación',
            subtitle: 'Clasificación de uso de suelo',
            icon: 'fas fa-map-marked-alt'
        },
        ambiental: {
            title: 'Ambiental',
            subtitle: 'Impacto ambiental y mitigación',
            icon: 'fas fa-leaf'
        },
        permisos: {
            title: 'Permisos y licencias',
            subtitle: 'Autorizaciones y licencias',
            icon: 'fas fa-file-signature'
        },
        aspectos: {
            title: 'Aspectos ambientales',
            subtitle: 'Normativas ambientales',
            icon: 'fas fa-balance-scale'
        },
        historico: {
            title: 'Histórico',
            subtitle: 'Conservación histórica y cultural',
            icon: 'fas fa-landmark'
        }
    };
    
    const specialist = specialists[specialistId] || specialists.general;
    
    const titleElement = document.getElementById('specialistTitle');
    const subtitleElement = document.getElementById('specialistDescription');
    
    if (titleElement) {
        titleElement.innerHTML = `<i class="${specialist.icon}"></i> ${specialist.title}`;
    }
    
    if (subtitleElement) {
        subtitleElement.textContent = specialist.subtitle;
    }
}

// ===== FUNCIONES DE UI =====
function clearChat() {
    const chatContainer = document.getElementById('chatContainer');
    if (chatContainer) {
        chatContainer.innerHTML = '';
    }
    AppState.chatHistory = [];
}

function showWelcomeMessage() {
    const welcomeMessage = document.getElementById('welcomeMessage');
    if (welcomeMessage) {
        welcomeMessage.style.display = 'block';
    }
}

function scrollToBottom(smooth = true) {
    const chatContainer = document.getElementById('chatContainer');
    if (!chatContainer) return;
    
    const scrollOptions = {
        top: chatContainer.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto'
    };
    
    chatContainer.scrollTo(scrollOptions);
}

function handleChatScroll() {
    // Lógica para manejar scroll si es necesario
    // Por ejemplo, marcar mensajes como leídos
}

// ===== SIDEBAR MÓVIL =====
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    if (sidebar && overlay) {
        sidebar.classList.toggle('open');
        overlay.classList.toggle('active');
    }
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    if (sidebar && overlay) {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
    }
}

// ===== SISTEMA DE TOASTS =====
function showToast(message, type = 'info', duration = 3000) {
    const toastContainer = document.getElementById('toastContainer');
    if (!toastContainer) return;
    
    const toastId = `toast-${Date.now()}`;
    const toastHtml = `
        <div class="toast ${type}" id="${toastId}">
            <div class="toast-content">
                <span>${escapeHtml(message)}</span>
                <button class="toast-close" onclick="removeToast('${toastId}')">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `;
    
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    
    // Auto-remove después del duration
    setTimeout(() => removeToast(toastId), duration);
}

function removeToast(toastId) {
    const toast = document.getElementById(toastId);
    if (toast) {
        toast.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }
}

// ===== UTILIDADES =====
function generateSessionId() {
    return 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

function formatTime(date) {
    return date.toLocaleTimeString('es-PR', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatBotResponse(text) {
    // Formato mejorado para respuestas conversacionales
    let formatted = escapeHtml(text);
    
    // 1. Convertir saltos de línea a párrafos para mejor legibilidad
    formatted = formatted.replace(/\n\n+/g, '</p><p>').replace(/\n/g, '<br>');
    formatted = '<p>' + formatted + '</p>';
    
    // 2. Formatear encabezados y secciones
    formatted = formatted.replace(/###\s*(.*?)(<br>|<\/p>)/g, '<h4 class="response-heading">$1</h4>');
    formatted = formatted.replace(/##\s*(.*?)(<br>|<\/p>)/g, '<h3 class="response-heading">$1</h3>');
    formatted = formatted.replace(/#\s*(.*?)(<br>|<\/p>)/g, '<h2 class="response-heading">$1</h2>');
    
    // 3. Formatear elementos importantes
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="highlight">$1</strong>');
    formatted = formatted.replace(/\*(.*?)\*/g, '<em class="emphasis">$1</em>');
    
    // 4. Formatear referencias a TOmos con estilo especial
    formatted = formatted.replace(/TOMO\s+(\d+)/gi, '<span class="tomo-reference">TOMO $1</span>');
    formatted = formatted.replace(/\[TOMO ([^\]]+)\]/g, '<span class="citation">📋 TOMO $1</span>');
    
    // 5. Formatear listas y viñetas
    formatted = formatted.replace(/^-\s+(.*?)(<br>|$)/gm, '<li class="list-item">$1</li>');
    formatted = formatted.replace(/(<li class="list-item">.*?<\/li>)/gs, '<ul class="response-list">$1</ul>');
    
    // 6. Formatear definiciones y conceptos clave
    formatted = formatted.replace(/([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ\s]{10,}?):/g, '<strong class="definition-term">$1:</strong>');
    
    // 7. Formatear artículos y referencias legales
    formatted = formatted.replace(/(Artículo|Art\.|Ley|Reglamento)\s+([^\s,.<]+)/g, '<span class="legal-reference">$1 $2</span>');
    
    // 8. Limpiar párrafos vacíos
    formatted = formatted.replace(/<p><\/p>/g, '').replace(/<p><br><\/p>/g, '');
    
    return formatted;
}

// ===== ATAJOS DE TECLADO =====
document.addEventListener('keydown', function(e) {
    // Ctrl+/ para enfocar input
    if (e.ctrlKey && e.key === '/') {
        e.preventDefault();
        const input = document.getElementById('messageInput');
        if (input) input.focus();
    }
    
    // Escape para cerrar sidebar en móvil
    if (e.key === 'Escape') {
        closeSidebar();
    }
});

// ===== MANEJO DE ERRORES GLOBALES =====
window.addEventListener('error', function(e) {
    console.error('Error global:', e.error);
    showToast('Error inesperado en la aplicación', 'error');
});

// ===== CSS DINÁMICAS ADICIONALES =====
const additionalStyles = `
    @keyframes slideOutRight {
        from {
            opacity: 1;
            transform: translateX(0);
        }
        to {
            opacity: 0;
            transform: translateX(100%);
        }
    }
    
    .toast-content {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
    }
    
    .toast-close {
        background: none;
        border: none;
        cursor: pointer;
        opacity: 0.7;
        padding: 4px;
        border-radius: 4px;
    }
    
    .toast-close:hover {
        opacity: 1;
        background: rgba(0,0,0,0.1);
    }
`;

// Agregar estilos adicionales
const styleSheet = document.createElement('style');
styleSheet.textContent = additionalStyles;
document.head.appendChild(styleSheet);

console.log('✅ JP_IA v4.0 - Sistema de Chat Moderno cargado completamente');
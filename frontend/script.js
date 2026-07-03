// API Configuration
const API_BASE_URL = window.location.origin;

// Helper function to round scores to 1 decimal place
function roundScore(score) {
    if (typeof score === 'number') {
        return Math.round(score * 10) / 10;
    }
    return score;
}

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const imageInput = document.getElementById('imageInput');
const imagePreview = document.getElementById('imagePreview');
const previewImg = document.getElementById('previewImg');
const analyzeBtn = document.getElementById('analyzeBtn');
const loading = document.getElementById('loading');
const resultsSection = document.getElementById('resultsSection');

// Preference selectors
const aestheticSelect = document.getElementById('aesthetic');
const nicheSelect = document.getElementById('niche');
const targetAudienceSelect = document.getElementById('targetAudience');
const contentTypeSelect = document.getElementById('contentType');
const brandVoiceSelect = document.getElementById('brandVoice');

// State
let selectedImage = null;
let preferences = null;
let enhancedImages = [];
let currentEnhancementIndex = 0;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    loadPreferences();
    setupEventListeners();
});

// Load available preferences from API
async function loadPreferences() {
    try {
        const response = await fetch(`${API_BASE_URL}/available-preferences`);
        if (response.ok) {
            const data = await response.json();
            populateSelects(data);
        } else {
            showError('Failed to load preferences. Make sure the API server is running.');
        }
    } catch (error) {
        console.error('Error loading preferences:', error);
        showError('Failed to connect to API server. Please start the server with: python api.py');
    }
}

// Populate preference dropdowns
function populateSelects(data) {
    // Populate aesthetics
    data.aesthetics.forEach(aesthetic => {
        const option = document.createElement('option');
        option.value = aesthetic;
        option.textContent = aesthetic;
        aestheticSelect.appendChild(option);
    });

    // Populate niches
    data.niches.forEach(niche => {
        const option = document.createElement('option');
        option.value = niche;
        option.textContent = niche;
        nicheSelect.appendChild(option);
    });

    // Populate target audiences
    data.target_audiences.forEach(audience => {
        const option = document.createElement('option');
        option.value = audience;
        option.textContent = audience;
        targetAudienceSelect.appendChild(option);
    });

    // Populate content types
    data.content_types.forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        contentTypeSelect.appendChild(option);
    });

    // Populate brand voices
    data.brand_voices.forEach(voice => {
        const option = document.createElement('option');
        option.value = voice;
        option.textContent = voice;
        brandVoiceSelect.appendChild(option);
    });
}

// Setup event listeners
function setupEventListeners() {
    // Upload area click
    uploadArea.addEventListener('click', () => {
        imageInput.click();
    });

    // File input change
    imageInput.addEventListener('change', handleImageSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // Analyze button
    analyzeBtn.addEventListener('click', analyzeImage);
}

// Handle image selection
function handleImageSelect(event) {
    const file = event.target.files[0];
    if (file) {
        processImageFile(file);
    }
}

// Handle drag over
function handleDragOver(event) {
    event.preventDefault();
    uploadArea.classList.add('dragover');
}

// Handle drag leave
function handleDragLeave(event) {
    event.preventDefault();
    uploadArea.classList.remove('dragover');
}

// Handle drop
function handleDrop(event) {
    event.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const files = event.dataTransfer.files;
    if (files.length > 0) {
        processImageFile(files[0]);
    }
}

// Process image file
async function processImageFile(file) {
    console.log('Processing file:', file.name, 'Type:', file.type, 'Size:', file.size);
    
    // Check if it's a HEIC/HEIF file (iPhone format)
    const fileName = file.name.toLowerCase();
    const isHeic = file.type === 'image/heic' || file.type === 'image/heif' || 
                   file.type === '' ||  // Some browsers don't recognize HEIC type
                   fileName.endsWith('.heic') || fileName.endsWith('.heif');
    
    // Validate file type - allow HEIC/HEIF for iPhone images
    if (!file.type.startsWith('image/') && !isHeic) {
        showError('Please select a valid image file.');
        return;
    }

    // Validate file size (10MB limit)
    if (file.size > 10 * 1024 * 1024) {
        showError('Image file size must be less than 10MB.');
        return;
    }

    // Show loading indicator for HEIC conversion
    if (isHeic) {
        console.log('HEIC file detected, attempting conversion...');
        showLoading('Converting iPhone image... This may take a few seconds.');
    }

    try {
        let imageFile = file;
        let conversionSucceeded = false;
        
        // Convert HEIC/HEIF to JPEG for preview (browsers don't support HEIC)
        if (isHeic) {
            if (typeof heic2any !== 'undefined') {
                console.log('heic2any library is available, converting...');
                try {
                    const convertedBlob = await heic2any({
                        blob: file,
                        toType: 'image/jpeg',
                        quality: 0.92
                    });
                    // heic2any may return an array or single blob
                    const jpegBlob = Array.isArray(convertedBlob) ? convertedBlob[0] : convertedBlob;
                    imageFile = new File([jpegBlob], fileName.replace(/\.heic$/i, '.jpg').replace(/\.heif$/i, '.jpg'), {
                        type: 'image/jpeg'
                    });
                    console.log('HEIC converted to JPEG successfully, new size:', imageFile.size);
                    conversionSucceeded = true;
                } catch (heicError) {
                    console.error('HEIC conversion failed:', heicError);
                }
            } else {
                console.warn('heic2any library not loaded');
            }
            
            // If conversion failed, show a message but continue
            // The backend can still process HEIC files
            if (!conversionSucceeded) {
                console.log('Will send original HEIC to backend for processing');
                // Show placeholder and continue - backend will handle it
                hideLoading();
                showError('iPhone image preview not available. Click "Analyze" to process the image.');
                previewImg.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2VlZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5pUGhvbmUgSW1hZ2U8L3RleHQ+PHRleHQgeD0iNTAlIiB5PSI2MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCIgZm9udC1zaXplPSIxMiIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPihIRUlDIEZvcm1hdCk8L3RleHQ+PC9zdmc+';
                imagePreview.style.display = 'block';
                selectedImage = file;  // Keep original for backend
                updateAnalyzeButton();
                return;
            }
        }

        // Hide loading if shown
        hideLoading();

        // Create preview
        const reader = new FileReader();
        reader.onload = function(e) {
            console.log('FileReader loaded, setting preview image');
            previewImg.src = e.target.result;
            imagePreview.style.display = 'block';
            selectedImage = imageFile;  // Use converted file if available
            updateAnalyzeButton();
        };
        reader.onerror = function(e) {
            console.error('FileReader error:', e);
            hideLoading();
            showError('Error reading image file.');
        };
        reader.readAsDataURL(imageFile);
    } catch (error) {
        hideLoading();
        console.error('Error processing image:', error);
        showError('Error processing image. Please try another image.');
    }
}

// Update analyze button state
function updateAnalyzeButton() {
    const hasImage = selectedImage !== null;
    
    analyzeBtn.disabled = !hasImage;
    
    if (hasImage) {
        analyzeBtn.innerHTML = '<i class="fas fa-magic"></i> Analyze Image';
    }
}

// Analyze image
async function analyzeImage() {
    console.log('analyzeImage() called');
    
    if (!selectedImage) {
        showError('Please select an image first.');
        return;
    }

    console.log('Selected image:', selectedImage.name, 'Size:', selectedImage.size, 'Type:', selectedImage.type);

    // Show loading
    loading.style.display = 'block';
    resultsSection.style.display = 'none';
    analyzeBtn.disabled = true;

    try {
        // Convert image to base64
        console.log('Converting image to base64...');
        const base64Image = await fileToBase64(selectedImage);
        console.log('Base64 conversion complete. Length:', base64Image.length);
        
        // Prepare request data (no user preferences per owner request)
        const requestData = {
            image: base64Image
        };
        
        console.log('Request data prepared.');
        console.log('Sending request to API:', `${API_BASE_URL}/score-image`);

        // Send request to API
        const response = await fetch(`${API_BASE_URL}/score-image`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });
        
        console.log('Response received:', response.status, response.statusText);

        if (response.ok) {
            const result = await response.json();
            console.log('API Response JSON:', JSON.stringify(result, null, 2));
            console.log('Response keys:', Object.keys(result));
            console.log('Has definition?', 'definition' in result);
            console.log('Has layout?', 'layout' in result);
            console.log('Has mood?', 'mood' in result);
            console.log('Has vibe_check?', 'vibe_check' in result);
            console.log('Calling displayResults...');
            displayResults(result);
            console.log('displayResults completed');
        } else {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Analysis failed');
        }

    } catch (error) {
        console.error('Analysis error:', error);
        showError(`Analysis failed: ${error.message}`);
    } finally {
        // Hide loading
        loading.style.display = 'none';
        analyzeBtn.disabled = false;
    }
}

// Convert file to base64
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            // Remove the data URL prefix (e.g., "data:image/jpeg;base64,")
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = error => reject(error);
    });
}

// Display results
function displayResults(result) {
    console.log('displayResults called with:', result);
    console.log('Result keys:', Object.keys(result));
    
    // Check if content was rejected
    if (result.status === 'rejected') {
        displayRejectedContent(result);
        return;
    }

    console.log('final_score:', result.final_score);
    console.log('definition:', result.definition);
    console.log('layout:', result.layout);
    console.log('mood:', result.mood);
    console.log('vibe_check:', result.vibe_check);

    // Update final score with rounding
    document.getElementById('finalScore').textContent = roundScore(result.final_score);

    // Update score breakdown with detailed sub-scores
    const scoreBreakdown = document.getElementById('scoreBreakdown');
    scoreBreakdown.innerHTML = '';

    const scoreCategories = [
        { 
            key: 'definition', 
            name: 'Definition', 
            icon: '🔧',
            subScoreLabels: {
                'sharpness_focus': 'Sharpness & Focus',
                'resolution_clarity': 'Resolution & Clarity',
                'image_noise': 'Image Noise',
                'dynamic_range': 'Dynamic Range',
                'color_fidelity': 'Color Fidelity'
            }
        },
        { 
            key: 'layout', 
            name: 'Layout', 
            icon: '📐',
            subScoreLabels: {
                'rule_of_thirds': 'Rule of Thirds',
                'leading_lines': 'Leading Lines',
                'balance_symmetry': 'Balance & Symmetry',
                'depth_framing': 'Depth & Framing',
                'subject_isolation': 'Subject Isolation'
            }
        },
        { 
            key: 'mood', 
            name: 'Mood', 
            icon: '🧠',
            subScoreLabels: {
                'presence_of_faces': 'Presence of Faces',
                'emotional_resonance': 'Emotional Resonance',
                'color_psychology': 'Color Psychology',
                'storytelling': 'Storytelling'
            }
        },
        { 
            key: 'vibe_check', 
            name: 'Vibe Check', 
            icon: '📈',
            subScoreLabels: {
                'aesthetic_alignment': 'Aesthetic Alignment',
                'authenticity_index': 'Authenticity Index'
            }
        }
    ];

    scoreCategories.forEach((category, index) => {
        const scoreData = result[category.key];
        
        // Defensive check - skip if category data is missing
        if (!scoreData) {
            console.error(`Missing data for category: ${category.key}`);
            console.error('Available keys in result:', Object.keys(result));
            return; // Skip this category
        }
        
        const card = document.createElement('div');
        card.className = 'score-card';
        
        // Build sub-scores HTML if available
        let subScoresHTML = '';
        if (scoreData.sub_scores && Object.keys(scoreData.sub_scores).length > 0) {
            subScoresHTML = '<div class="sub-scores-container collapsed" id="subScores_' + index + '">';
            for (const [key, value] of Object.entries(scoreData.sub_scores)) {
                const label = category.subScoreLabels[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                const scoreValue = roundScore(value);
                const scoreClass = scoreValue >= 80 ? 'high' : scoreValue >= 60 ? 'medium' : 'low';
                subScoresHTML += `
                    <div class="sub-score-item">
                        <span class="sub-score-label">${label}</span>
                        <div class="sub-score-bar-container">
                            <div class="sub-score-bar ${scoreClass}" style="width: ${scoreValue}%"></div>
                        </div>
                        <span class="sub-score-value">${scoreValue}</span>
                    </div>
                `;
            }
            subScoresHTML += '</div>';
        }
        
        // Build feedback HTML (Creative Coach)
        let feedbackHTML = '';
        if (scoreData.feedback) {
            feedbackHTML = `
                <div class="creative-coach-feedback">
                    <span class="coach-icon">💡</span>
                    <span class="coach-text">${scoreData.feedback}</span>
                </div>
            `;
        }
        
        const weightPercent = scoreData.weight_percent || (scoreData.weight * 100) + '%';
        
        card.innerHTML = `
            <div class="score-card-header" onclick="toggleSubScores(${index})">
                <h4>${category.icon} ${category.name}</h4>
                <span class="weight-badge">${weightPercent}</span>
                <span class="expand-icon" id="expandIcon_${index}">▼</span>
            </div>
            <div class="score-value">${roundScore(scoreData.score)}/100</div>
            <div class="score-progress-bar">
                <div class="score-progress" style="width: ${scoreData.score}%"></div>
            </div>
            ${subScoresHTML}
            ${feedbackHTML}
            <div class="score-details">${scoreData.details}</div>
        `;
        scoreBreakdown.appendChild(card);
    });

    // Hide recommendations section (removed per owner request)
    const recommendationsSection = document.querySelector('.recommendations');
    if (recommendationsSection) {
        recommendationsSection.style.display = 'none';
    }

    // Show results
    resultsSection.style.display = 'block';
    
    // Always add enhancement button (removed score < 80 restriction)
    addEnhancementButton();
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Toggle sub-scores visibility
function toggleSubScores(index) {
    const subScoresContainer = document.getElementById('subScores_' + index);
    const expandIcon = document.getElementById('expandIcon_' + index);
    
    if (subScoresContainer) {
        if (subScoresContainer.classList.contains('collapsed')) {
            subScoresContainer.classList.remove('collapsed');
            subScoresContainer.classList.add('expanded');
            if (expandIcon) expandIcon.textContent = '▲';
        } else {
            subScoresContainer.classList.remove('expanded');
            subScoresContainer.classList.add('collapsed');
            if (expandIcon) expandIcon.textContent = '▼';
        }
    }
}

// Make toggleSubScores globally available
window.toggleSubScores = toggleSubScores;

// Display rejected content message
function displayRejectedContent(result) {
    // Update final score to show 0
    document.getElementById('finalScore').textContent = '0';
    document.getElementById('finalScore').style.color = '#e74c3c';

    // Clear score breakdown
    const scoreBreakdown = document.getElementById('scoreBreakdown');
    scoreBreakdown.innerHTML = '';

    // Create rejection message card
    const rejectionCard = document.createElement('div');
    rejectionCard.className = 'score-card rejection-card';
    rejectionCard.innerHTML = `
        <h4>🚫 Content Rejected</h4>
        <div class="rejection-message">
            <p><strong>${result.message}</strong></p>
            <p><em>Reason: ${result.rejection_reason}</em></p>
        </div>
    `;
    scoreBreakdown.appendChild(rejectionCard);

    // Add risk analysis card if moderation details are available
    if (result.moderation_details && result.moderation_details.risk_scores) {
        const riskCard = document.createElement('div');
        riskCard.className = 'score-card risk-analysis-card';
        
        const riskScores = result.moderation_details.risk_scores;
        const violations = result.moderation_details.violations || [];
        
        let riskContent = '<h4>🔍 Risk Analysis</h4>';
        riskContent += '<div class="risk-scores">';
        
        // Display risk scores
        const riskCategories = [
            { key: 'adult', name: 'Adult Content', icon: '🔞' },
            { key: 'violence', name: 'Violence', icon: '⚔️' },
            { key: 'racy', name: 'Racy Content', icon: '💋' },
            { key: 'medical', name: 'Medical Content', icon: '🏥' },
            { key: 'spoof', name: 'Spoof/Manipulated', icon: '🎭' }
        ];
        
        riskCategories.forEach(category => {
            const score = riskScores[category.key] || 0;
            const riskLevel = getRiskLevelText(score);
            const riskClass = getRiskClass(score);
            
            riskContent += `
                <div class="risk-item ${riskClass}">
                    <span class="risk-icon">${category.icon}</span>
                    <span class="risk-name">${category.name}</span>
                    <span class="risk-score">${score}/5</span>
                    <span class="risk-level">${riskLevel}</span>
                </div>
            `;
        });
        
        riskContent += '</div>';
        
        // Display violations if any
        if (violations.length > 0) {
            riskContent += '<div class="violations-section">';
            riskContent += '<h5>🚨 Detected Violations:</h5>';
            riskContent += '<ul class="violations-list">';
            violations.forEach(violation => {
                riskContent += `<li>${violation}</li>`;
            });
            riskContent += '</ul>';
            riskContent += '</div>';
        }
        
        riskCard.innerHTML = riskContent;
        scoreBreakdown.appendChild(riskCard);
    }

    // Update recommendations with content guidelines
    const recommendationList = document.getElementById('recommendationList');
    recommendationList.innerHTML = '';
    
    if (result.recommendations && result.recommendations.length > 0) {
        result.recommendations.forEach(recommendation => {
            const li = document.createElement('li');
            li.textContent = recommendation;
            recommendationList.appendChild(li);
        });
    }

    // Show results
    resultsSection.style.display = 'block';
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

// Helper function to get risk level text
function getRiskLevelText(score) {
    switch(score) {
        case 0: return 'Unknown';
        case 1: return 'Very Unlikely';
        case 2: return 'Unlikely';
        case 3: return 'Possible';
        case 4: return 'Likely';
        case 5: return 'Very Likely';
        default: return 'Unknown';
    }
}

// Helper function to get risk class for styling
function getRiskClass(score) {
    if (score >= 4) return 'high-risk';
    if (score >= 3) return 'medium-risk';
    return 'low-risk';
}

// Add enhancement button to results
function addEnhancementButton() {
    const resultsSection = document.getElementById('resultsSection');
    
    // Remove existing enhancement section
    const existingSection = document.getElementById('enhancementControls');
    if (existingSection) {
        existingSection.remove();
    }
    
    // Create enhancement controls section (no custom prompt - only available after enhancement)
    const enhancementControls = document.createElement('div');
    enhancementControls.id = 'enhancementControls';
    enhancementControls.className = 'enhancement-controls-section';
    enhancementControls.innerHTML = `
        <div class="enhancement-options">
            <label for="numVersions">Number of Enhanced Versions:</label>
            <select id="numVersions" class="num-versions-select">
                <option value="1">1 Version</option>
                <option value="2" selected>2 Versions</option>
                <option value="3">3 Versions</option>
                <option value="4">4 Versions</option>
                <option value="5">5 Versions (Max)</option>
            </select>
        </div>
        <button id="enhancementBtn" class="enhancement-btn">
            <i class="fas fa-magic"></i> Enhance Image with AI
        </button>
    `;
    
    // Insert after score display
    const scoreDisplay = document.querySelector('.score-display');
    
    if (scoreDisplay && scoreDisplay.parentNode) {
        scoreDisplay.parentNode.insertBefore(enhancementControls, scoreDisplay.nextSibling);
    } else {
        // Fallback: append to results section
        resultsSection.appendChild(enhancementControls);
    }
    
    // Add event listener to the button
    document.getElementById('enhancementBtn').onclick = enhanceImage;
    
    console.log('Enhancement controls added to page');
}

// Enhance image with AI
async function enhanceImage() {
    if (!selectedImage) {
        showError('Please select an image first.');
        return;
    }
    
    // Get the selected number of versions
    const numVersionsSelect = document.getElementById('numVersions');
    const numVersions = numVersionsSelect ? parseInt(numVersionsSelect.value) : 1;
    
    // Show loading
    const loading = document.getElementById('loading');
    loading.style.display = 'block';
    loading.querySelector('p').textContent = `Generating ${numVersions} enhanced image${numVersions > 1 ? 's' : ''} with AI...`;
    
    const enhancementBtn = document.getElementById('enhancementBtn');
    if (enhancementBtn) {
        enhancementBtn.disabled = true;
    }
    
    try {
        // Convert image to base64
        const base64Image = await fileToBase64(selectedImage);
        
        // Prepare request data (no custom prompt for initial enhancement)
        const requestData = {
            image: base64Image,
            num_versions: numVersions
        };
        
        // Always use standard enhancement endpoint (custom prompt only after enhancement)
        const apiEndpoint = `${API_BASE_URL}/enhance-image`;
        console.log('Using standard enhancement endpoint (no custom prompt)');
        
        console.log('Sending enhancement request with num_versions:', numVersions);
        
        // Send enhancement request
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('Enhancement response:', result);
            console.log('Enhanced images array:', result.enhanced_images);
            console.log('Enhanced images array length:', result.enhanced_images ? result.enhanced_images.length : 'undefined');
            
            // Check if enhanced_images exists and has data
            if (!result.enhanced_images || result.enhanced_images.length === 0) {
                throw new Error('No enhanced images returned from server');
            }
            
            // Log first image data for debugging
            if (result.enhanced_images[0]) {
                console.log('First image has image data:', result.enhanced_images[0].image ? 'yes (length: ' + result.enhanced_images[0].image.length + ')' : 'no');
                console.log('First image score:', result.enhanced_images[0].score);
            }
            
            enhancedImages = result.enhanced_images;
            currentEnhancementIndex = 0;
            
            if (enhancedImages.length > 0) {
                console.log('Calling displayEnhancedImages...');
                displayEnhancedImages();
                console.log('displayEnhancedImages completed');
            } else {
                showError('No enhanced images were generated.');
            }
        } else {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Enhancement failed');
        }
        
    } catch (error) {
        console.error('Enhancement error:', error);
        showError(`Enhancement failed: ${error.message}`);
    } finally {
        // Hide loading
        loading.style.display = 'none';
        loading.querySelector('p').textContent = 'Analyzing your image with AI...';
        
        if (enhancementBtn) {
            enhancementBtn.disabled = false;
        }
    }
}

// Display enhanced images
function displayEnhancedImages() {
    const resultsSection = document.getElementById('resultsSection');
    
    // Remove existing enhancement section
    const existingEnhancement = document.getElementById('enhancementSection');
    if (existingEnhancement) {
        existingEnhancement.remove();
    }
    
    // Create enhancement section
    const enhancementSection = document.createElement('div');
    enhancementSection.id = 'enhancementSection';
    enhancementSection.className = 'enhancement-section';
    
    const currentImage = enhancedImages[currentEnhancementIndex];
    const score = currentImage.score || 0;
    const scoreClass = score >= 80 ? 'high-score' : score >= 60 ? 'medium-score' : 'low-score';
    
    // Create score comparison HTML for all versions
    let scoreComparisonHTML = '<div class="score-comparison">';
    scoreComparisonHTML += '<h4>📊 All Versions Comparison</h4>';
    scoreComparisonHTML += '<div class="score-comparison-grid">';
    
    enhancedImages.forEach((img, idx) => {
        const imgScore = roundScore(img.score || 0);
        const imgScoreClass = imgScore >= 80 ? 'high-score' : imgScore >= 60 ? 'medium-score' : 'low-score';
        const isActive = idx === currentEnhancementIndex ? 'active' : '';
        
        scoreComparisonHTML += `
            <div class="score-comparison-item ${isActive} ${imgScoreClass}" onclick="jumpToEnhancedImage(${idx})">
                <div class="version-label">Version ${idx + 1}</div>
                <div class="version-score">${imgScore}/100</div>
                ${isActive ? '<div class="viewing-badge">👁️ Viewing</div>' : ''}
            </div>
        `;
    });
    
    scoreComparisonHTML += '</div></div>';
    
    const roundedScore = roundScore(score);
    
    enhancementSection.innerHTML = `
        <h3><i class="fas fa-star"></i> AI Enhanced Images</h3>
        ${scoreComparisonHTML}
        <div class="enhancement-controls">
            <button class="nav-btn" onclick="previousEnhancedImage()" id="prevBtn">
                <i class="fas fa-chevron-left"></i>
            </button>
            <span class="enhancement-counter">${currentEnhancementIndex + 1} / ${enhancedImages.length}</span>
            <button class="nav-btn" onclick="nextEnhancedImage()" id="nextBtn">
                <i class="fas fa-chevron-right"></i>
            </button>
        </div>
        <div class="enhancement-display">
            <div class="original-image">
                <h4>Original</h4>
                <img src="${previewImg.src}" alt="Original" class="comparison-img">
            </div>
            <div class="enhanced-image">
                <h4>Enhanced Version ${currentEnhancementIndex + 1}</h4>
                <div class="enhanced-score ${scoreClass}">
                    <span class="score-label">ai_image_scorer Score:</span>
                    <span class="score-number">${roundedScore}/100</span>
                </div>
                <img src="data:image/jpeg;base64,${currentImage.image}" alt="Enhanced" class="comparison-img" id="currentEnhancedImg">
            </div>
        </div>
        <div class="enhancement-actions">
            <button class="action-btn reject-btn" onclick="rejectEnhancedImage()">
                <i class="fas fa-times"></i> Discard
            </button>
            <button class="action-btn save-btn" onclick="saveEnhancedImage()">
                <i class="fas fa-save"></i> Save
            </button>
        </div>
        <div class="re-enhancement-section">
            <h5>✨ Want to enhance this further?</h5>
            <div class="enhancement-options custom-prompt-section">
                <label for="reEnhancePrompt">Additional Enhancement Instructions:</label>
                <textarea id="reEnhancePrompt" 
                    placeholder="E.g., 'Make it even more vibrant' or 'Add a softer filter'..."
                    rows="2"></textarea>
                <small class="prompt-hint">💡 This will create a new version based on the current enhanced image</small>
            </div>
            <button class="action-btn re-enhance-btn" onclick="reEnhanceCurrentImage()">
                <i class="fas fa-magic"></i> Re-enhance This Image
            </button>
        </div>
        <div class="enhancement-prompt">
            <h5>Enhancement Details:</h5>
            <p>${currentImage.prompt}</p>
        </div>
    `;
    
    resultsSection.appendChild(enhancementSection);
    enhancementSection.scrollIntoView({ behavior: 'smooth' });
    
    updateEnhancementControls();
}

// Re-enhance the currently displayed enhanced image
window.reEnhanceCurrentImage = async function() {
    const currentImage = enhancedImages[currentEnhancementIndex];
    const reEnhancePromptInput = document.getElementById('reEnhancePrompt');
    const customPrompt = reEnhancePromptInput ? reEnhancePromptInput.value.trim() : '';
    
    if (!customPrompt) {
        showError('Please enter enhancement instructions to re-enhance this image.');
        return;
    }
    
    // Show loading
    const loading = document.getElementById('loading');
    loading.style.display = 'block';
    loading.querySelector('p').textContent = 'Re-enhancing this image with your new instructions...';
    
    const reEnhanceBtn = document.querySelector('.re-enhance-btn');
    if (reEnhanceBtn) {
        reEnhanceBtn.disabled = true;
    }
    
    try {
        // Use the enhanced image as the source
        const base64Image = currentImage.image;
        
        // Prepare request data for custom enhancement
        const requestData = {
            image: base64Image,
            num_versions: 1,  // Generate just 1 new version
            custom_prompt: customPrompt  // Required for custom endpoint
        };
        
        console.log('Re-enhancing image with custom prompt:', customPrompt);
        
        // Send enhancement request to CUSTOM PROMPT endpoint
        const response = await fetch(`${API_BASE_URL}/custom-prompt`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestData)
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('Re-enhancement response:', result);
            
            if (result.enhanced_images && result.enhanced_images.length > 0) {
                // Add the new enhanced version to our array
                const newEnhancedImage = result.enhanced_images[0];
                newEnhancedImage.version = enhancedImages.length + 1; // Assign new version number
                enhancedImages.push(newEnhancedImage);
                
                // Jump to the new image
                currentEnhancementIndex = enhancedImages.length - 1;
                displayEnhancedImages();
                
                // Clear the re-enhance prompt
                if (reEnhancePromptInput) {
                    reEnhancePromptInput.value = '';
                }
                
                showSuccess(`New enhanced version created! (Version ${newEnhancedImage.version})`);
            } else {
                showError('No enhanced images were generated.');
            }
        } else {
            const errorData = await response.json();
            throw new Error(errorData.detail || 'Re-enhancement failed');
        }
        
    } catch (error) {
        console.error('Re-enhancement error:', error);
        showError(`Re-enhancement failed: ${error.message}`);
    } finally {
        // Hide loading
        loading.style.display = 'none';
        loading.querySelector('p').textContent = 'Analyzing your image with AI...';
        
        if (reEnhanceBtn) {
            reEnhanceBtn.disabled = false;
        }
    }
};

// Navigation functions for enhanced images
window.previousEnhancedImage = function() {
    if (currentEnhancementIndex > 0) {
        currentEnhancementIndex--;
        displayEnhancedImages();
    }
};

window.nextEnhancedImage = function() {
    if (currentEnhancementIndex < enhancedImages.length - 1) {
        currentEnhancementIndex++;
        displayEnhancedImages();
    }
};

window.jumpToEnhancedImage = function(index) {
    if (index >= 0 && index < enhancedImages.length) {
        currentEnhancementIndex = index;
        displayEnhancedImages();
    }
};

window.rejectEnhancedImage = function() {
    // Remove current enhanced image from array
    enhancedImages.splice(currentEnhancementIndex, 1);
    
    if (enhancedImages.length === 0) {
        // No more enhanced images
        const enhancementSection = document.getElementById('enhancementSection');
        if (enhancementSection) {
            enhancementSection.remove();
        }
        showSuccess('All enhanced images have been discarded.');
    } else {
        // Adjust index if needed
        if (currentEnhancementIndex >= enhancedImages.length) {
            currentEnhancementIndex = enhancedImages.length - 1;
        }
        displayEnhancedImages();
    }
};

window.saveEnhancedImage = function() {
    const enhancedImage = enhancedImages[currentEnhancementIndex];
    
    // Create download link
    const link = document.createElement('a');
    link.href = `data:image/jpeg;base64,${enhancedImage.image}`;
    link.download = `enhanced_image_v${enhancedImage.version}.jpg`;
    link.click();
    
    showSuccess(`Enhanced image version ${enhancedImage.version} saved successfully!`);
};

// Update enhancement navigation controls
function updateEnhancementControls() {
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const counter = document.querySelector('.enhancement-counter');
    
    if (prevBtn) prevBtn.disabled = currentEnhancementIndex === 0;
    if (nextBtn) nextBtn.disabled = currentEnhancementIndex === enhancedImages.length - 1;
    if (counter) counter.textContent = `${currentEnhancementIndex + 1} / ${enhancedImages.length}`;
}

// Show error message
function showError(message) {
    // Remove existing error messages
    const existingError = document.querySelector('.error');
    if (existingError) {
        existingError.remove();
    }

    // Create error element
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`;
    
    // Insert after header
    const mainContent = document.querySelector('.main-content');
    mainContent.insertBefore(errorDiv, mainContent.firstChild);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (errorDiv.parentNode) {
            errorDiv.remove();
        }
    }, 5000);
}

// Show success message
function showSuccess(message) {
    // Remove existing success messages
    const existingSuccess = document.querySelector('.success');
    if (existingSuccess) {
        existingSuccess.remove();
    }

    // Create success element
    const successDiv = document.createElement('div');
    successDiv.className = 'success';
    successDiv.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    
    // Insert after header
    const mainContent = document.querySelector('.main-content');
    mainContent.insertBefore(successDiv, mainContent.firstChild);
    
    // Auto-remove after 3 seconds
    setTimeout(() => {
        if (successDiv.parentNode) {
            successDiv.remove();
        }
    }, 3000);
}

// Show loading overlay with message
function showLoading(message = 'Processing...') {
    // Remove existing loading overlay
    hideLoading();
    
    // Create loading overlay
    const loadingOverlay = document.createElement('div');
    loadingOverlay.id = 'loadingOverlay';
    loadingOverlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;
    loadingOverlay.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 10px; text-align: center;">
            <i class="fas fa-spinner fa-spin" style="font-size: 2rem; color: #667eea; margin-bottom: 10px;"></i>
            <p style="margin: 0; color: #333;">${message}</p>
        </div>
    `;
    document.body.appendChild(loadingOverlay);
}

// Hide loading overlay
function hideLoading() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.remove();
    }
}

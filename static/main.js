document.addEventListener('DOMContentLoaded', () => {
    const settingsModal = new bootstrap.Modal(document.getElementById('settingsModal'));
    const imageDetailModal = new bootstrap.Modal(document.getElementById('imageDetailModal'));
    
    document.getElementById('imageDetailModal').addEventListener('shown.bs.modal', () => {
        const metadataContainer = document.getElementById('metadata-container');
        if (metadataContainer) {
            metadataContainer.scrollTop = 0;
        }
    });

    const gallery = document.getElementById('image-gallery');
    const loadingIndicator = document.getElementById('loading-indicator');
    const searchInput = document.getElementById('searchInput');
    const sortSelect = document.getElementById('sortSelect');
    const platformSelect = document.getElementById('platformSelect');

    let currentPage = 1;
    let currentQuery = '';
    let currentSort = 'random';
    let currentPlatformFilter = 'all';
    let isLoading = false;
    let hasMore = true;

    // --- Core Functions ---

    const fetchImages = async (page = 1, query = '', sort_by = 'random', platform_filter = 'all') => {
        if (isLoading || (page > 1 && !hasMore)) return;

        isLoading = true;
        loadingIndicator.style.display = 'block';

        try {
            const response = await axios.get(`/api/images?page=${page}&limit=30&query=${query}&sort_by=${sort_by}&platform_filter=${platform_filter}`);
            const data = response.data;

            if (page === 1) {
                gallery.innerHTML = '';
            }

            renderGallery(data.images);
            currentPage = data.page;
            hasMore = data.page < data.total_pages;

            if (data.images.length === 0 && page === 1) {
                gallery.innerHTML = '<p class="text-center col-12">No images found. Try scanning or changing your search.</p>';
            }

        } catch (error) {
            console.error('Failed to fetch images:', error);
            if (error.response && error.response.status === 404 && page === 1) {
                settingsModal.show();
            }
        } finally {
            isLoading = false;
            loadingIndicator.style.display = 'none';
        }
    };

    const renderGallery = (images) => {
        images.forEach(image => {
            const col = document.createElement('div');
            col.className = 'col-6 col-sm-4 col-md-3 col-lg-2';
            col.innerHTML = `
                <div class="card bg-secondary gallery-item" data-image-id="${image.no}">
                    <img src="${image.filepath}" class="card-img-top" alt="Image ${image.no}" loading="lazy">
                    <div class="platform-overlay">${image.platform}</div>
                </div>
            `;
            gallery.appendChild(col);
        });
    };
    
    const renderMetadata = (metadata) => {
        const mainContainer = document.createElement('div');
        const longItemsContainer = document.createElement('div');
        const shortItemsContainer = document.createElement('div');
        shortItemsContainer.className = 'd-flex flex-wrap gap-2';

        let parsedMeta = {};

        if (metadata.Software === 'StableDiffusion' && typeof metadata.prompt === 'string') {
            const promptStr = metadata.prompt;
            const negPromptIndex = promptStr.indexOf('Negative prompt:');
            const stepsIndex = promptStr.indexOf('Steps:');

            parsedMeta.prompt = negPromptIndex > -1 ? promptStr.substring(0, negPromptIndex).trim() : promptStr;
            
            if (negPromptIndex > -1) {
                const negPromptStr = stepsIndex > -1 ? promptStr.substring(negPromptIndex, stepsIndex) : promptStr.substring(negPromptIndex);
                parsedMeta['Negative prompt'] = negPromptStr.replace('Negative prompt:', '').trim();
            }

            if (stepsIndex > -1) {
                const settingsStr = promptStr.substring(stepsIndex);
                const settingsArray = settingsStr.split(/,(?=(?:[^\"]*"[^\"]*")*[^\"]*$)/g);
                settingsArray.forEach(setting => {
                    const parts = setting.split(':');
                    const key = parts[0].trim();
                    const value = parts.slice(1).join(':').trim();
                    if (key) {
                        parsedMeta[key] = value;
                    }
                });
            }
        } else {
            parsedMeta = metadata;
        }

        const longItemKeys = ['prompt', 'negative prompt', 'uc'];
        for (const key in parsedMeta) {
            const value = parsedMeta[key];
            if (value === null || value === undefined || String(value).trim() === '') {
                continue;
            }

            if (longItemKeys.includes(key.toLowerCase()) || String(value).length > 80) {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'mb-3 position-relative';
                
                const label = document.createElement('label');
                label.className = 'form-label fw-bold';
                label.textContent = key;
                itemDiv.appendChild(label);
                
                const textarea = document.createElement('textarea');
                textarea.className = 'form-control bg-dark text-light';
                textarea.textContent = value;
                textarea.rows = Math.min(10, Math.ceil(String(value).length / 80));
                textarea.readOnly = true;
                itemDiv.appendChild(textarea);

                // 긴 항목 옆에는 항상 복사 버튼 표시
                const copyBtn = document.createElement('button');
                copyBtn.className = 'btn btn-sm btn-outline-secondary copy-btn';
                copyBtn.textContent = 'Copy';
                copyBtn.onclick = () => {
                    navigator.clipboard.writeText(value).then(() => {
                        copyBtn.textContent = 'Copied!';
                        setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
                    });
                };
                itemDiv.appendChild(copyBtn);
                longItemsContainer.appendChild(itemDiv);
            } else {
                // 짧은 항목 옆에는 복사 버튼을 표시하지 않습니다.
                const shortItemDiv = document.createElement('div');
                shortItemDiv.className = 'short-item p-2 bg-dark rounded position-relative';
                shortItemDiv.innerHTML = `<span class="text-muted me-2">${key}:</span><strong>${value}</strong>`;
                shortItemsContainer.appendChild(shortItemDiv);
            }
        }
        
        mainContainer.appendChild(longItemsContainer);
        if (shortItemsContainer.hasChildNodes()) {
            const separator = document.createElement('hr');
            const shortItemsHeader = document.createElement('h6');
            shortItemsHeader.className = 'mt-3';
            shortItemsHeader.textContent = 'Details';
            mainContainer.appendChild(separator);
            mainContainer.appendChild(shortItemsHeader);
            mainContainer.appendChild(shortItemsContainer);
        }

        return mainContainer;
    };

    const fetchImageDetails = async (id) => {
        try {
            const response = await axios.get(`/api/images/${id}`);
            const image = response.data;
            document.getElementById('detailImage').src = image.filepath;
            
            const metadataContainer = document.getElementById('metadata-container');
            metadataContainer.innerHTML = ''; // Clear previous content
            metadataContainer.appendChild(renderMetadata(image.metadata));
            
            imageDetailModal.show();
        } catch (error) {
            console.error('Failed to fetch image details:', error);
        }
    };


    // --- Event Handlers ---

    document.getElementById('saveSettingsButton').addEventListener('click', async () => {
        const config = {
            image_file_path: document.getElementById('image_file_path').value,
            des_file_path: document.getElementById('des_file_path').value,
        };
        try {
            await axios.post('/api/config', config);
            settingsModal.hide();
            location.reload(); // Reload to apply settings
        } catch (error) {
            alert(`Failed to save settings: ${error.response.data.detail}`);
        }
    });

    document.getElementById('scanButton').addEventListener('click', async () => {
        if (confirm('Start scanning for new images in the source directory? This may take a while.')) {
            try {
                await axios.post('/api/scan');
                alert('Image scan started in the background.');
            } catch (error) {
                alert(`Failed to start scan: ${error.response.data.detail}`);
            }
        }
    });

    const handleSearch = () => {
        const query = searchInput.value;
        const sort_by = sortSelect.value;
        const platform_filter = platformSelect.value;
        
        currentQuery = query;
        currentSort = sort_by;
        currentPlatformFilter = platform_filter;
        currentPage = 1;
        hasMore = true;
        gallery.innerHTML = '';
        fetchImages(currentPage, currentQuery, currentSort, currentPlatformFilter);
    };

    document.getElementById('searchButton').addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            handleSearch();
        }
    });

    sortSelect.addEventListener('change', handleSearch);
    platformSelect.addEventListener('change', handleSearch);

    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 200) {
            if (hasMore && !isLoading) {
                fetchImages(currentPage + 1, currentQuery, currentSort, currentPlatformFilter);
            }
        }
    });

    gallery.addEventListener('click', (e) => {
        const card = e.target.closest('.gallery-item');
        if (card) {
            const imageId = card.dataset.imageId;
            fetchImageDetails(imageId);
        }
    });


    // --- Initialization ---
    const checkConfigAndInit = async () => {
        try {
            const response = await axios.get('/api/config');
            const config = response.data;
            document.getElementById('image_file_path').value = config.image_file_path;
            document.getElementById('des_file_path').value = config.des_file_path;
            handleSearch();
        } catch (error) {
            if (error.response && error.response.status === 404) {
                settingsModal.show();
            } else {
                console.error('An unexpected error occurred:', error);
            }
        }
    };

    checkConfigAndInit();
});

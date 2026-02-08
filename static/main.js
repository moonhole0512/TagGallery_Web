document.addEventListener('DOMContentLoaded', () => {
    const VERSION = "1.0.2 - Structural Fix";
    console.log(`%c TAG GALLERY JS LOADED - VERSION: ${VERSION} `, 'background: #222; color: #bada55; font-size: 1.2em; padding: 5px;');

    if (typeof bootstrap === 'undefined') {
        alert('Bootstrap library failed to load. Please check your internet connection and refresh.');
        return;
    }

    // --- Helper for safe element access ---
    const getEl = (id) => {
        const el = document.getElementById(id);
        if (!el) console.warn(`Element with ID "${id}" not found.`);
        return el;
    };

    // --- UI Elements ---
    const settingsModalEl = getEl('settingsModal');
    const imageDetailModalEl = getEl('imageDetailModal');

    const settingsModal = settingsModalEl ? new bootstrap.Modal(settingsModalEl) : null;
    const imageDetailModal = imageDetailModalEl ? new bootstrap.Modal(imageDetailModalEl) : null;

    const gallery = getEl('image-gallery');
    const loadingIndicator = getEl('loading-indicator');
    const searchInput = getEl('searchInput');
    const sortSelect = getEl('sortSelect');
    const platformSelect = getEl('platformSelect');
    const deleteModeButton = getEl('deleteModeButton');
    const favoriteOnlyCheckbox = getEl('favoriteOnlyCheckbox');
    const videoOnlyCheckbox = getEl('videoOnlyCheckbox');

    // --- State Variables ---
    let currentPage = 1;
    let currentQuery = '';
    let currentSort = 'random';
    let currentPlatformFilter = 'all';
    let currentVideoOnly = false;
    let currentFavoriteOnly = false;
    let currentSeed = null;
    let isLoading = false;
    let hasMore = true;
    let currentImages = [];
    let currentImageIndex = -1;
    let columns = [];
    let columnCount = 0;

    let isSelectionMode = false;
    let selectedImageIds = new Set();
    let scanPollingInterval = null;

    // --- Zoom State ---
    let currentZoom = 1;
    let isPanning = false;
    let startPanX = 0, startPanY = 0;
    let currentPanX = 0, currentPanY = 0;

    // --- Core Functions ---

    const initColumns = () => {
        const width = window.innerWidth;
        let newCount = 6;
        if (width < 600) newCount = 2;
        else if (width < 850) newCount = 3;
        else if (width < 1100) newCount = 4;
        else if (width < 1400) newCount = 5;

        if (newCount !== columnCount || (gallery && gallery.children.length === 0)) {
            columnCount = newCount;
            if (gallery) {
                gallery.innerHTML = '';
                columns = [];
                for (let i = 0; i < columnCount; i++) {
                    const col = document.createElement('div');
                    col.className = 'gallery-column';
                    gallery.appendChild(col);
                    columns.push(col);
                }
            }
            if (currentImages.length > 0) {
                const imagesToRedraw = [...currentImages];
                currentImages = [];
                renderGallery(imagesToRedraw);
            }
        }
    };

    const fetchImages = async (page = 1, query = '', sort_by = 'random', platform_filter = 'all', seed = null, video_only = false, favorites_only = false) => {
        if (isLoading || (page > 1 && !hasMore)) return;
        isLoading = true;
        if (loadingIndicator) loadingIndicator.style.display = 'block';

        try {
            let url = `/api/images?page=${page}&limit=40&query=${query}&sort_by=${sort_by}&platform_filter=${platform_filter}&video_only=${video_only}&favorites_only=${favorites_only}`;
            if (seed !== null) url += `&seed=${seed}`;

            const response = await axios.get(url);
            const data = response.data;

            if (page === 1) {
                if (gallery) gallery.innerHTML = '';
                currentImages = [];
                initColumns();
            }

            renderGallery(data.images);
            currentPage = data.page;
            hasMore = data.page < data.total_pages;

            if (data.images.length === 0 && page === 1 && gallery) {
                gallery.innerHTML = '<p class="text-center w-100 p-5">No images found.</p>';
            }
        } catch (error) {
            console.error('Failed to fetch images:', error);
        } finally {
            isLoading = false;
            if (loadingIndicator) loadingIndicator.style.display = 'none';
        }
    };

    const renderGallery = (images) => {
        if (columns.length === 0) initColumns();

        images.forEach(image => {
            if (!currentImages.find(img => img.no === image.no)) {
                currentImages.push(image);
            }

            const wrapper = document.createElement('div');
            wrapper.className = 'gallery-item-wrapper';

            const isVideo = image.filepath.toLowerCase().endsWith('.mp4') ||
                image.filepath.toLowerCase().endsWith('.webm') ||
                image.filepath.toLowerCase().endsWith('.gif');

            const thumbUrl = isVideo ? image.filepath + ".thumb.jpg" : image.filepath;
            const heartIcon = image.is_favorite ? '❤️' : '🤍';

            wrapper.innerHTML = `
                <div class="card bg-secondary gallery-item" data-image-id="${image.no}">
                    <img src="${thumbUrl}" class="card-img-top" alt="Image ${image.no}" loading="lazy" onerror="this.src='${image.filepath}'; this.onerror=null;">
                    <div class="platform-overlay">${image.platform}</div>
                    <div class="favorite-btn position-absolute top-0 start-0 m-2 fs-5" style="z-index: 10;">${heartIcon}</div>
                    ${isVideo ? '<div class="video-overlay">VIDEO</div>' : ''}
                    <div class="selection-overlay"></div>
                </div>
            `;

            const shortestColumn = columns.reduce((prev, curr) =>
                prev.children.length <= curr.children.length ? prev : curr
            );
            shortestColumn.appendChild(wrapper);

            wrapper.querySelector('.favorite-btn').addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                toggleFavorite(image.no, !image.is_favorite);
            });
        });
        updateGalleryVisuals();
    };

    const parseSDParameters = (params_str) => {
        if (!params_str || typeof params_str !== 'string') return null;
        // SD parameters usually contain "Steps: " or "Negative prompt: "
        if (!params_str.includes('Steps: ') && !params_str.includes('Negative prompt: ')) return null;

        const metadata = {};
        const parts = params_str.split('Negative prompt: ');
        let paramsLine = "";

        if (parts.length > 1) {
            metadata['prompt'] = parts[0].trim();
            const remaining = parts[1];
            const lines = remaining.split('\n');
            if (lines.length > 1) {
                metadata['negative prompt'] = lines.slice(0, -1).join('\n').trim();
                paramsLine = lines[lines.length - 1];
            } else {
                if (remaining.includes('Steps: ')) {
                    const pParts = remaining.split('Steps: ');
                    metadata['negative prompt'] = pParts[0].trim();
                    paramsLine = 'Steps: ' + pParts[1];
                } else {
                    metadata['negative prompt'] = remaining.trim();
                }
            }
        } else {
            if (params_str.includes('Steps: ')) {
                const pParts = params_str.split('Steps: ');
                metadata['prompt'] = pParts[0].trim();
                paramsLine = 'Steps: ' + pParts[1];
            } else {
                metadata['prompt'] = params_str.trim();
            }
        }

        if (paramsLine) {
            // Regex to split key-value pairs while trying to respect words that look like keys
            const pairs = paramsLine.split(/, (?=[A-Z][a-zA-Z0-9\s]+: )/);
            pairs.forEach(pair => {
                const colonIdx = pair.indexOf(':');
                if (colonIdx !== -1) {
                    const k = pair.substring(0, colonIdx).trim();
                    let v = pair.substring(colonIdx + 1).trim();
                    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
                        v = v.substring(1, v.length - 1);
                    }
                    metadata[k] = v;
                }
            });
        }
        return metadata;
    };

    const adjustMetadataHeights = () => {
        document.querySelectorAll('.metadata-textarea').forEach(textarea => {
            textarea.style.height = 'auto';
            textarea.style.height = (textarea.scrollHeight + 2) + 'px';
        });
    };

    const renderMetadata = (metadata) => {
        let displayMetadata = { ...metadata };

        // If it's SD and only has a 'prompt' field that looks like a full parameter block, parse it
        if (metadata.Software === 'StableDiffusion' && metadata.prompt && Object.keys(metadata).length <= 2) {
            const parsed = parseSDParameters(metadata.prompt);
            if (parsed) {
                displayMetadata = { ...parsed, Software: 'StableDiffusion' };
            }
        }

        const mainContainer = document.createElement('div');
        const longItemsContainer = document.createElement('div');
        const shortItemsContainer = document.createElement('div');
        shortItemsContainer.className = 'd-flex flex-wrap gap-2';

        const keys = Object.keys(displayMetadata);
        keys.forEach(key => {
            const value = displayMetadata[key];
            if (!value || String(value).trim() === '') return;

            if (String(value).length > 80 || ['prompt', 'uc', 'negative prompt'].includes(key.toLowerCase())) {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'mb-3 position-relative';
                itemDiv.innerHTML = `
                    <div class="metadata-item-header">
                        <label class="form-label fw-bold mb-0">${key}</label>
                        <button class="btn btn-sm btn-outline-info copy-btn-new">Copy</button>
                    </div>
                    <textarea class="form-control bg-dark text-light metadata-textarea" readonly>${value}</textarea>
                `;

                const textarea = itemDiv.querySelector('textarea');
                const btn = itemDiv.querySelector('.copy-btn-new');

                btn.onclick = () => {
                    navigator.clipboard.writeText(value).then(() => {
                        const originalText = 'Copy';
                        btn.textContent = 'Copied!';
                        btn.classList.replace('btn-outline-info', 'btn-success');
                        setTimeout(() => {
                            btn.textContent = originalText;
                            btn.classList.replace('btn-success', 'btn-outline-info');
                        }, 2000);
                    });
                };

                longItemsContainer.appendChild(itemDiv);

                // Auto-resize logic
                setTimeout(() => {
                    textarea.style.height = 'auto';
                    textarea.style.height = (textarea.scrollHeight + 2) + 'px';
                }, 0);
            } else {
                const shortDiv = document.createElement('div');
                shortDiv.className = 'short-item p-1 px-2 bg-dark rounded border border-secondary small';
                shortDiv.innerHTML = `<span class="text-muted small">${key}:</span> <strong>${value}</strong>`;
                shortItemsContainer.appendChild(shortDiv);
            }
        });

        mainContainer.appendChild(longItemsContainer);
        if (shortItemsContainer.children.length > 0) {
            mainContainer.appendChild(document.createElement('hr'));
            mainContainer.appendChild(shortItemsContainer);
        }
        return mainContainer;
    };

    const toggleFavorite = async (id, isFavorite) => {
        try {
            await axios.post(`/api/images/${id}/favorite?favorite=${isFavorite}`);
            const found = currentImages.find(img => img.no === id);
            if (found) found.is_favorite = isFavorite;

            document.querySelectorAll(`.gallery-item[data-image-id="${id}"] .favorite-btn`).forEach(btn => {
                btn.textContent = isFavorite ? '❤️' : '🤍';
            });

            document.querySelectorAll(`.discovery-item[data-image-id="${id}"] .sidebar-fav-btn`).forEach(btn => {
                btn.textContent = isFavorite ? '❤️' : '🤍';
            });

            const detailFavBtn = getEl('detailFavoriteBtn');
            if (detailFavBtn && currentImageIndex !== -1 && currentImages[currentImageIndex].no === id) {
                detailFavBtn.textContent = isFavorite ? '❤️' : '🤍';
                detailFavBtn.classList.toggle('detail-favorite-active', isFavorite);
            }
        } catch (error) {
            console.error('Failed to toggle favorite:', error);
        }
    };

    const resetZoom = () => {
        currentZoom = 1;
        currentPanX = 0;
        currentPanY = 0;
        updateZoomTransform();
    };

    const updateZoomTransform = (isActuallyPanning = false) => {
        const w = getEl('zoomWrapper');
        if (w) {
            // Disable transition during panning for 1:1 responsiveness
            w.style.transition = isActuallyPanning ? 'none' : 'transform 0.2s ease-out';
            w.style.transform = `translate(${currentPanX}px, ${currentPanY}px) scale(${currentZoom})`;
        }
    };

    const pollScanStatus = async () => {
        try {
            const res = await axios.get('/api/scan/status');
            const status = res.data;
            const container = getEl('scanProgressContainer');
            const bar = getEl('scanProgressBar');
            const text = getEl('scanProgressText');

            if (!container || !bar || !text) return;

            if (status.is_running) {
                container.classList.remove('d-none');
                bar.style.width = `${status.total > 0 ? (status.current / status.total) * 100 : 0}%`;
                text.textContent = `${status.message} (${status.current}/${status.total})`;
            } else if (status.message.includes('완료')) {
                bar.style.width = '100%';
                text.textContent = status.message;
                setTimeout(() => container.classList.add('d-none'), 3000);
                clearInterval(scanPollingInterval);
                scanPollingInterval = null;
            } else {
                container.classList.add('d-none');
                clearInterval(scanPollingInterval);
                scanPollingInterval = null;
            }
        } catch (e) { console.error(e); }
    };

    const fetchSimilarImages = async (image_id) => {
        const container = getEl('similar-images-container');
        if (!container) return;

        container.innerHTML = '<div class="text-center py-5"><div class="spinner-border spinner-border-sm text-info"></div></div>';

        try {
            const response = await axios.get(`/api/images/${image_id}/similar`);
            const similarImages = response.data;
            container.innerHTML = '';

            if (similarImages.length === 0) {
                container.innerHTML = '<div class="text-muted text-center py-4 small">No similar images found</div>';
                return;
            }

            similarImages.forEach(img => {
                const item = document.createElement('div');
                item.className = 'discovery-item';
                item.dataset.imageId = img.no;

                const isV = img.filepath.toLowerCase().endsWith('.mp4') ||
                    img.filepath.toLowerCase().endsWith('.webm') ||
                    img.filepath.toLowerCase().endsWith('.gif');

                const tUrl = isV ? (img.filepath.endsWith('.thumb.jpg') ? img.filepath : img.filepath + ".thumb.jpg") : img.filepath;

                item.innerHTML = `
                    <img src="${tUrl}" alt="similar">
                    ${img.platform && img.platform !== 'Unknown' ? `<span class="platform-badge">${img.platform}</span>` : ''}
                    <button class="btn btn-sm sidebar-fav-btn">${img.is_favorite ? '❤️' : '🤍'}</button>
                `;

                const favBtn = item.querySelector('.sidebar-fav-btn');
                favBtn.onclick = (e) => {
                    e.stopPropagation();
                    toggleFavorite(img.no, !img.is_favorite);
                };

                item.onclick = (e) => {
                    e.stopPropagation();
                    if (!currentImages.find(i => i.no === img.no)) {
                        currentImages.push(img);
                    }
                    currentImageIndex = currentImages.findIndex(i => i.no === img.no);
                    fetchImageDetails(img.no);
                    container.scrollTop = 0;
                };
                container.appendChild(item);
            });
        } catch (error) {
            console.error('Failed to fetch similar images:', error);
            container.innerHTML = '<div class="text-danger small">Failed to load</div>';
        }
    };

    const fetchImageDetails = async (id) => {
        try {
            console.log('Fetching image details for ID:', id);
            const response = await axios.get(`/api/images/${id}`);
            const image = response.data;

            const detailContainer = getEl('zoomWrapper');
            if (!detailContainer) return;

            const isVideo = image.filepath.toLowerCase().endsWith('.mp4') ||
                image.filepath.toLowerCase().endsWith('.webm') ||
                image.filepath.toLowerCase().endsWith('.gif');

            detailContainer.innerHTML = '';
            resetZoom();

            // Auto-fetch similar images for the sidebar
            fetchSimilarImages(id);

            if (isVideo) {
                const video = document.createElement('video');
                video.id = 'detailVideo';
                video.src = image.filepath;
                video.className = 'img-fluid';
                video.controls = true;
                video.autoplay = true;
                video.loop = true;
                video.style.maxHeight = '60vh';
                video.style.objectFit = 'contain';
                detailContainer.appendChild(video);
            } else {
                const img = document.createElement('img');
                img.id = 'detailImage';
                img.src = image.filepath;
                img.className = 'img-fluid';
                img.alt = 'Detailed view';
                img.style.maxHeight = '60vh';
                img.style.objectFit = 'contain';
                img.draggable = false;
                detailContainer.appendChild(img);
            }

            const metaCont = getEl('metadata-container');
            if (metaCont) {
                metaCont.innerHTML = '';
                metaCont.appendChild(renderMetadata(image.metadata));
            }

            const detailFavBtn = getEl('detailFavoriteBtn');
            if (detailFavBtn) {
                detailFavBtn.textContent = image.is_favorite ? '❤️' : '🤍';
                detailFavBtn.classList.toggle('detail-favorite-active', image.is_favorite);
                detailFavBtn.onclick = () => toggleFavorite(id, !image.is_favorite);
            }

            if (imageDetailModal) imageDetailModal.show();
        } catch (error) {
            console.error('Failed to fetch image details:', error);
            alert('Failed to load image details. Check console.');
        }
    };

    // --- Navigation & Selection ---
    const navigateImage = (direction) => {
        if (currentImages.length === 0 || currentImageIndex === -1) return;
        let nextIndex = currentImageIndex + direction;
        if (nextIndex < 0) return;
        if (nextIndex >= currentImages.length) {
            if (hasMore && !isLoading) {
                fetchImages(currentPage + 1, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly, currentFavoriteOnly).then(() => {
                    if (nextIndex < currentImages.length) {
                        currentImageIndex = nextIndex;
                        fetchImageDetails(currentImages[currentImageIndex].no);
                    }
                });
            }
            return;
        }
        currentImageIndex = nextIndex;
        fetchImageDetails(currentImages[currentImageIndex].no);
    };

    const updateGalleryVisuals = () => {
        document.querySelectorAll('.gallery-item').forEach(card => {
            const id = parseInt(card.dataset.imageId);
            card.classList.toggle('selected-for-deletion', isSelectionMode && selectedImageIds.has(id));
        });
        if (deleteModeButton) {
            deleteModeButton.textContent = isSelectionMode ? `Delete (${selectedImageIds.size})` : 'Delete';
            deleteModeButton.classList.toggle('btn-warning', isSelectionMode && selectedImageIds.size > 0);
        }
    };

    const executeDeletion = async () => {
        if (selectedImageIds.size === 0 || !confirm(`${selectedImageIds.size}개의 이미지를 삭제하시겠습니까?`)) return;
        try {
            await axios.delete('/api/images/batch', { data: { image_ids: [...selectedImageIds] } });
            selectedImageIds.clear();
            isSelectionMode = false;
            handleSearch();
        } catch (error) {
            alert('삭제 실패: ' + error.message);
        }
    };

    // --- Search & Polling ---
    const handleSearch = () => {
        currentQuery = searchInput ? searchInput.value : '';
        currentSort = sortSelect ? sortSelect.value : 'random';
        currentPlatformFilter = platformSelect ? platformSelect.value : 'all';
        currentVideoOnly = videoOnlyCheckbox ? videoOnlyCheckbox.checked : false;
        currentFavoriteOnly = favoriteOnlyCheckbox ? favoriteOnlyCheckbox.checked : false;
        currentSeed = currentSort === 'random' ? Math.floor(Math.random() * 1000000) : null;
        currentPage = 1;
        hasMore = true;
        fetchImages(1, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly, currentFavoriteOnly);
    };

    // --- Event Listeners ---
    const saveBtn = getEl('saveSettingsButton');
    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const config = {
                image_file_path: getEl('image_file_path')?.value || '',
                des_file_path: getEl('des_file_path')?.value || '',
            };
            try {
                await axios.post('/api/config', config);
                if (settingsModal) settingsModal.hide();
                location.reload();
            } catch (error) {
                alert(`Failed to save settings: ${error.response?.data?.detail || error.message}`);
            }
        });
    }

    const searchBtn = getEl('searchButton');
    if (searchBtn) searchBtn.onclick = handleSearch;
    if (searchInput) searchInput.onkeypress = (e) => { if (e.key === 'Enter') handleSearch(); };

    [sortSelect, platformSelect, videoOnlyCheckbox, favoriteOnlyCheckbox].forEach(el => {
        if (el) el.onchange = handleSearch;
    });

    const scanBtn = getEl('scanButton');
    if (scanBtn) {
        scanBtn.onclick = async () => {
            if (!confirm('Scan for new images?')) return;
            await axios.post('/api/scan');
            if (!scanPollingInterval) scanPollingInterval = setInterval(pollScanStatus, 1000);
        };
    }

    if (getEl('prevImageBtn')) getEl('prevImageBtn').onclick = () => navigateImage(-1);
    if (getEl('nextImageBtn')) getEl('nextImageBtn').onclick = () => navigateImage(1);
    if (getEl('showSimilarBtn')) getEl('showSimilarBtn').onclick = () => {
        if (currentImageIndex !== -1) fetchSimilarImages(currentImages[currentImageIndex].no);
    };

    if (deleteModeButton) {
        deleteModeButton.onclick = () => {
            if (isSelectionMode && selectedImageIds.size > 0) executeDeletion();
            else { isSelectionMode = !isSelectionMode; selectedImageIds.clear(); updateGalleryVisuals(); }
        };
    }

    if (gallery) {
        gallery.onclick = (e) => {
            const card = e.target.closest('.gallery-item');
            if (!card) return;
            const id = parseInt(card.dataset.imageId);
            if (isSelectionMode) {
                if (selectedImageIds.has(id)) selectedImageIds.delete(id);
                else selectedImageIds.add(id);
                updateGalleryVisuals();
            } else {
                currentImageIndex = currentImages.findIndex(img => img.no === id);
                fetchImageDetails(id);
            }
        };
    }

    document.addEventListener('keydown', (e) => {
        const modal = getEl('imageDetailModal');
        if (modal && modal.classList.contains('show')) {
            if (e.key === 'ArrowLeft') navigateImage(-1);
            else if (e.key === 'ArrowRight') navigateImage(1);
        }
    });

    let lastMouseDownX = 0;
    let lastMouseDownY = 0;

    const zw = getEl('zoomWrapper');
    if (zw) {
        zw.ondragstart = (e) => e.preventDefault(); // Disable default drag behavior
        zw.onmousedown = (e) => {
            lastMouseDownX = e.clientX;
            lastMouseDownY = e.clientY;

            if (currentZoom > 1) {
                e.preventDefault(); // Prevent text selection and default drag
                isPanning = true;
                startPanX = e.clientX - currentPanX;
                startPanY = e.clientY - currentPanY;
                zw.style.cursor = 'grabbing';
            }
        };
        window.onmousemove = (e) => {
            if (isPanning) {
                currentPanX = e.clientX - startPanX;
                currentPanY = e.clientY - startPanY;
                updateZoomTransform(true);
            }
        };
        window.onmouseup = (e) => {
            const moveDist = Math.sqrt(Math.pow(e.clientX - lastMouseDownX, 2) + Math.pow(e.clientY - lastMouseDownY, 2));

            if (isPanning) {
                isPanning = false;
                zw.style.cursor = 'grab';
                updateZoomTransform(false); // Restore transition
            }

            // Always check for click-to-reset, even if we were prep-ing for a pan
            if (moveDist < 5 && (currentZoom !== 1 || currentPanX !== 0 || currentPanY !== 0)) {
                resetZoom();
            }
        };
        zw.onwheel = (e) => {
            e.preventDefault();
            const d = e.deltaY > 0 ? -0.1 : 0.1;
            if (currentZoom + d > 0.2) {
                currentZoom += d;
                updateZoomTransform();
            }
        };
        zw.style.cursor = 'grab';
    }

    window.onresize = () => { clearTimeout(window.resTimer); window.resTimer = setTimeout(initColumns, 200); };

    window.addEventListener('scroll', () => {
        if (window.innerHeight + window.scrollY >= document.body.offsetHeight - 800) {
            if (hasMore && !isLoading) {
                fetchImages(currentPage + 1, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly, currentFavoriteOnly);
            }
        }
    });

    const detMod = getEl('imageDetailModal');
    if (detMod) {
        detMod.addEventListener('shown.bs.modal', () => {
            const mc = getEl('metadata-container');
            if (mc) mc.scrollTop = 0;
            adjustMetadataHeights();
        });
    }

    const loadConfigToUI = async () => {
        try {
            const response = await axios.get('/api/config');
            const cfg = response.data;
            if (getEl('image_file_path')) getEl('image_file_path').value = cfg.image_file_path || '';
            if (getEl('des_file_path')) getEl('des_file_path').value = cfg.des_file_path || '';
        } catch (e) {
            if (e.response?.status === 404 && settingsModal) {
                settingsModal.show();
            }
        }
    };

    const setModEl = getEl('settingsModal');
    if (setModEl) setModEl.addEventListener('show.bs.modal', loadConfigToUI);

    // --- Init ---
    (async () => {
        await loadConfigToUI();
        try {
            const status = (await axios.get('/api/scan/status')).data;
            if (status.is_running) scanPollingInterval = setInterval(pollScanStatus, 1000);
            handleSearch();
        } catch (e) { console.error('Init error:', e); }
    })();
});

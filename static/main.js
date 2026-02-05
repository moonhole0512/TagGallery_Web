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
    const deleteModeButton = document.getElementById('deleteModeButton'); // 새로운 버튼

    let currentPage = 1;
    let currentQuery = '';
    let currentSort = 'random';
    let currentPlatformFilter = 'all';
    let currentVideoOnly = false;
    let currentSeed = null;
    let isLoading = false;
    let hasMore = true;
    let currentImages = []; // 현재 표시 중인 이미지 목록 트래킹
    let currentImageIndex = -1; // 현재 모달에 표시 중인 이미지 인덱스
    let columns = []; // 컬럼 DOM 요소들
    let columnCount = 0;

    // --- 삭제 모드 관련 전역 변수 ---
    let isSelectionMode = false;
    let selectedImageIds = new Set(); // Set을 사용하여 중복 방지 및 빠른 검색
    // ----------------------------

    // --- Core Functions ---

    const initColumns = () => {
        const width = window.innerWidth;
        let newCount = 6;
        if (width < 600) newCount = 2;
        else if (width < 850) newCount = 3;
        else if (width < 1100) newCount = 4;
        else if (width < 1400) newCount = 5;

        // 컬럼 수가 변했거나 초기화가 필요한 경우
        if (newCount !== columnCount || gallery.children.length === 0) {
            console.log('Initializing columns:', newCount);
            columnCount = newCount;
            gallery.innerHTML = '';
            columns = [];
            for (let i = 0; i < columnCount; i++) {
                const col = document.createElement('div');
                col.className = 'gallery-column';
                gallery.appendChild(col);
                columns.push(col);
            }

            // 만약 기존 이미지가 있다면 재배치
            if (currentImages.length > 0) {
                const imagesToRedraw = [...currentImages];
                currentImages = []; // renderGallery에서 다시 채움
                renderGallery(imagesToRedraw);
            }
        }
    };

    const fetchImages = async (page = 1, query = '', sort_by = 'random', platform_filter = 'all', seed = null, video_only = false) => {
        if (isLoading || (page > 1 && !hasMore)) return;

        isLoading = true;
        loadingIndicator.style.display = 'block';

        try {
            let url = `/api/images?page=${page}&limit=30&query=${query}&sort_by=${sort_by}&platform_filter=${platform_filter}&video_only=${video_only}`;
            if (seed !== null) {
                url += `&seed=${seed}`;
            }
            const response = await axios.get(url);
            const data = response.data;

            if (page === 1) {
                gallery.innerHTML = '';
                currentImages = [];
                initColumns();
            }

            renderGallery(data.images);
            currentPage = data.page;
            hasMore = data.page < data.total_pages;

            if (data.images.length === 0 && page === 1) {
                gallery.innerHTML = '<p class="text-center w-100">No images found.</p>';
            }

        } catch (error) {
            console.error('Failed to fetch images:', error);
        } finally {
            isLoading = false;
            loadingIndicator.style.display = 'none';
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

            wrapper.innerHTML = `
                <div class="card bg-secondary gallery-item" data-image-id="${image.no}">
                    <img src="${thumbUrl}" class="card-img-top" alt="Image ${image.no}" loading="lazy" onerror="this.src='${image.filepath}'; this.onerror=null;">
                    <div class="platform-overlay">${image.platform}</div>
                    ${isVideo ? '<div class="video-overlay">VIDEO</div>' : ''}
                    <div class="selection-overlay"></div>
                </div>
            `;

            // 순차적으로 배분 (높이가 낮을 곳을 찾는 대신 가장 자수 가구가 적은 컬럼 선택)
            const shortestColumn = columns.reduce((prev, curr) =>
                prev.children.length <= curr.children.length ? prev : curr
            );
            shortestColumn.appendChild(wrapper);
        });
        updateGalleryVisuals();
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
                const negPromptStr = stepsIndex > -1 ? promptStr.substring(negPromptIndex, stepsIndex) : promptStr;
                parsedMeta['Negative prompt'] = negPromptStr.replace('Negative prompt:', '').trim();
            }

            if (stepsIndex > -1) {
                const settingsStr = promptStr.substring(stepsIndex);
                const settingsArray = settingsStr.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/g);
                settingsArray.forEach(setting => {
                    const parts = setting.split(':');
                    const key = parts[0].trim();
                    const value = parts.slice(1).join(':').trim();
                    if (key) {
                        parsedMeta[key] = value;
                    }
                });
            }
        } else if (metadata.Software === 'ComfyUI') {
            // ComfyUI metadata handling
            if (metadata.prompt) {
                // Try to find positive/negative prompts from ComfyUI nodes
                // Often in CLIPTextEncode nodes
                let positivePrompts = [];
                let negativePrompts = [];

                for (let nodeId in metadata.prompt) {
                    const node = metadata.prompt[nodeId];
                    if (node.class_type === 'CLIPTextEncode' || node.class_type === 'CLIPTextEncodeSDXL') {
                        const text = node.inputs.text || node.inputs.text_g || "";
                        if (text.toLowerCase().includes('negative') || text.toLowerCase().includes('low quality') || text.toLowerCase().includes('bad anatomy')) {
                            negativePrompts.push(text);
                        } else {
                            positivePrompts.push(text);
                        }
                    }
                }

                if (positivePrompts.length > 0) parsedMeta.prompt = positivePrompts.join('\n---\n');
                if (negativePrompts.length > 0) parsedMeta['Negative prompt'] = negativePrompts.join('\n---\n');

                parsedMeta['Full Workflow (JSON)'] = JSON.stringify(metadata.prompt, null, 2);
                if (metadata.workflow) {
                    parsedMeta['Visual Workflow (JSON)'] = JSON.stringify(metadata.workflow, null, 2);
                }
            } else {
                parsedMeta = metadata;
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

            const detailContainer = document.querySelector('#imageDetailModal .col-12.text-center.mb-3');
            const isVideo = image.filepath.toLowerCase().endsWith('.mp4') ||
                image.filepath.toLowerCase().endsWith('.webm') ||
                image.filepath.toLowerCase().endsWith('.gif');

            detailContainer.innerHTML = '';
            if (isVideo) {
                const video = document.createElement('video');
                video.id = 'detailVideo';
                video.src = image.filepath;
                video.className = 'img-fluid w-100';
                video.controls = true;
                video.autoplay = true;
                video.loop = true;
                video.style.maxHeight = '70vh';
                video.style.objectFit = 'contain';
                detailContainer.appendChild(video);
            } else {
                const img = document.createElement('img');
                img.id = 'detailImage';
                img.src = image.filepath;
                img.className = 'img-fluid w-100';
                img.alt = 'Detailed view';
                img.style.maxHeight = '70vh';
                img.style.objectFit = 'contain';
                detailContainer.appendChild(img);
            }

            const metadataContainer = document.getElementById('metadata-container');
            metadataContainer.innerHTML = ''; // Clear previous content
            metadataContainer.appendChild(renderMetadata(image.metadata));

            imageDetailModal.show();
        } catch (error) {
            console.error('Failed to fetch image details:', error);
        }
    };

    const navigateImage = (direction) => {
        if (currentImages.length === 0 || currentImageIndex === -1) return;

        let nextIndex = currentImageIndex + direction;

        // 범위 체크
        if (nextIndex < 0) return;
        if (nextIndex >= currentImages.length) {
            // 더 불러올 데이터가 있다면 시도
            if (hasMore && !isLoading) {
                fetchImages(currentPage + 1, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly).then(() => {
                    // 성공적으로 불러왔다면 다시 시도
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

    // --- 갤러리 시각적 상태 업데이트 함수 ---
    const updateGalleryVisuals = () => {
        console.log('updateGalleryVisuals called. isSelectionMode:', isSelectionMode, 'selectedImageIds.size:', selectedImageIds.size);
        document.querySelectorAll('.gallery-item').forEach(card => {
            const imageId = parseInt(card.dataset.imageId);
            if (isSelectionMode && selectedImageIds.has(imageId)) {
                card.classList.add('selected-for-deletion');
            } else {
                card.classList.remove('selected-for-deletion');
            }
        });

        // deleteModeButton 텍스트 업데이트
        if (isSelectionMode) {
            deleteModeButton.textContent = `Delete (${selectedImageIds.size})`;
            if (selectedImageIds.size > 0) {
                deleteModeButton.classList.remove('btn-danger');
                deleteModeButton.classList.add('btn-warning');
            } else {
                deleteModeButton.classList.remove('btn-warning');
                deleteModeButton.classList.add('btn-danger');
            }
        } else {
            deleteModeButton.textContent = 'Delete';
            deleteModeButton.classList.remove('btn-warning');
            deleteModeButton.classList.add('btn-danger');
        }
    };

    // --- 삭제 실행 함수 ---
    const executeDeletion = async () => {
        if (selectedImageIds.size === 0) {
            alert('삭제할 이미지를 선택하세요.');
            return;
        }

        if (!confirm(`${selectedImageIds.size}개의 이미지를 휴지통으로 이동하시겠습니까?`)) {
            return;
        }

        try {
            const response = await axios.delete('/api/images/batch', {
                data: { image_ids: Array.from(selectedImageIds) }
            });
            alert(response.data.message);

            // 삭제 후 갤러리 새로고침 및 선택 모드 종료
            selectedImageIds.clear();
            isSelectionMode = false;
            handleSearch(); // 전체 갤러리 새로고침
            updateGalleryVisuals(); // 버튼 텍스트 초기화 등
        } catch (error) {
            console.error('Failed to delete images:', error);
            alert(`이미지 삭제 실패: ${error.response.data.detail || error.message}`);
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
                const progress = document.getElementById('scanProgress');
                if (progress) progress.classList.remove('d-none');

                await axios.post('/api/scan');
                alert('Image scan started in the background.');

                // 스캔 시작 후 일정 시간 뒤에 스피너 숨김 (실제 완료 체크 로직이 없으므로 임시)
                setTimeout(() => {
                    if (progress) progress.classList.add('d-none');
                }, 5000);
            } catch (error) {
                alert(`Failed to start scan: ${error.response.data.detail}`);
                const progress = document.getElementById('scanProgress');
                if (progress) progress.classList.add('d-none');
            }
        }
    });

    const handleSearch = () => {
        const query = searchInput.value;
        const sort_by = sortSelect.value;
        const platform_filter = platformSelect.value;
        const video_only = document.getElementById('videoOnlyCheckbox').checked;

        currentQuery = query;
        currentSort = sort_by;
        currentPlatformFilter = platform_filter;
        currentVideoOnly = video_only;

        // 정렬이 random일 때만 새로운 시드 생성
        if (sort_by === 'random') {
            currentSeed = Math.floor(Math.random() * 1000000);
        } else {
            currentSeed = null;
        }

        currentPage = 1;
        hasMore = true;
        gallery.innerHTML = '';
        fetchImages(currentPage, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly);
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
                fetchImages(currentPage + 1, currentQuery, currentSort, currentPlatformFilter, currentSeed, currentVideoOnly);
            }
        }
    });

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            initColumns();
        }, 200);
    });

    // --- Keyboard Navigation ---
    document.addEventListener('keydown', (e) => {
        // 모달이 열려 있을 때만 동작
        const modalEl = document.getElementById('imageDetailModal');
        const isOpen = modalEl.classList.contains('show');

        if (isOpen) {
            if (e.key === 'ArrowLeft') {
                navigateImage(-1);
            } else if (e.key === 'ArrowRight') {
                navigateImage(1);
            }
            // ESC는 부트스트랩이 알아서 처리함
        }
    });

    document.getElementById('prevImageBtn').addEventListener('click', () => navigateImage(-1));
    document.getElementById('nextImageBtn').addEventListener('click', () => navigateImage(1));

    document.getElementById('videoOnlyCheckbox').addEventListener('change', handleSearch);

    gallery.addEventListener('click', (e) => {
        const card = e.target.closest('.gallery-item');
        if (!card) return;

        const imageId = parseInt(card.dataset.imageId);

        if (isSelectionMode) {
            // 선택 모드에서는 이미지 선택/해제
            e.preventDefault();
            e.stopPropagation(); // 상세 모달 열림 방지
            console.log('Selection mode: Toggling imageId', imageId);
            if (selectedImageIds.has(imageId)) {
                selectedImageIds.delete(imageId);
            } else {
                selectedImageIds.add(imageId);
            }
            updateGalleryVisuals(); // 시각적 상태 업데이트
        } else {
            // 일반 모드에서는 상세 이미지 보기
            currentImageIndex = currentImages.findIndex(img => img.no === imageId);
            console.log('Normal mode: Fetching details for imageId', imageId, 'index', currentImageIndex);
            fetchImageDetails(imageId);
        }
    });

    // --- deleteModeButton 클릭 이벤트 핸들러 ---
    deleteModeButton.addEventListener('click', () => {
        console.log('Delete button clicked. Current isSelectionMode:', isSelectionMode);
        if (isSelectionMode) {
            // 삭제 실행 모드에서 버튼 클릭 시 삭제 수행
            if (selectedImageIds.size === 0) {
                // 선택된 이미지가 없으면 삭제 모드 취소
                isSelectionMode = false;
                selectedImageIds.clear();
                updateGalleryVisuals();
                alert('선택된 이미지가 없으므로 삭제 모드를 취소합니다.');
            } else {
                executeDeletion();
            }
        } else {
            // 일반 모드에서 버튼 클릭 시 선택 모드 진입
            isSelectionMode = true;
            selectedImageIds.clear(); // 기존 선택 초기화
            updateGalleryVisuals();
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

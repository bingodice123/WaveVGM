let playingAudioId = null;

function getUniqueListenedStats(audio) {
    const ranges = audio.played; // Native browser TimeRanges object
    let totalSecondsListened = 0;

    // Loop through each distinct fragment the user actually played
    for (let i = 0; i < ranges.length; i++) {
        totalSecondsListened += ranges.end(i) - ranges.start(i);
    }

    const totalDuration = audio.duration || 0;
    const percentListened = totalDuration > 0 ? (totalSecondsListened / totalDuration) : 0;

    return {
        seconds: totalSecondsListened,
        percent: percentListened
    };
}

async function sendAnalytics(type, id, amount) {
    const payload = {type, id, amount};
    console.log(payload)
    try {
        const response = await fetch('/api/send-analytics', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!result.success) {
            console.error("Error sending analytics. Error: The server sent back an invalid response.")
        }

    } catch (error) {
        console.error("Error sending analytics. Error: ", error)
    }
}

function sendRetentionPercent() {
    const audio = document.querySelector('#vgm-audio')
        const payload = {type: 'retention_percent', amount: getUniqueListenedStats(audio)["percent"], id: playingAudioId}
        fetch('/api/send-analytics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            keepalive: true // Crucial property
        });
}

window.addEventListener('pagehide', () => {

    if (playingAudioId) {
        const payload = {type: 'exits', amount: 1, id: playingAudioId}
        fetch('/api/send-analytics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            keepalive: true // Crucial property
        });
    }
});

window.addEventListener('pagehide', () => {

    if (playingAudioId) {
        const audio = document.querySelector('#vgm-audio')
        const payload = {type: 'retention_percent', amount: getUniqueListenedStats(audio)["percent"], id: playingAudioId}
        fetch('/api/send-analytics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            keepalive: true // Crucial property
        });
    }
});


// Play audio 50% Gemini
function playAudio(stream, imgSrc = 'https://i.imgur.com/x6GQBYz.jpeg', title = 'Unknown', game = 'Unknown', songId) {
    // Me
    if (playingAudioId) {
        sendRetentionPercent()
    }

    // Gemini

    // 1. Select the media slot element nested inside media-chrome
    const mediaController = document.querySelector('#media-controls');
    if (mediaController.style.display === 'none') {
        mediaController.style.display = 'flex';
    }
    // Me
    const blurredThumbnailImg = document.getElementById('blurred-thumbnail-img');
    const mainThumbnailImg = document.getElementById('main-thumbnail-img');
    blurredThumbnailImg.style.setProperty('--bg-image', `url(${imgSrc})`);
    mainThumbnailImg.src = imgSrc;
    const mediaTitle = document.getElementById('media-title');
    const mediaDesc = document.getElementById('media-desc');
    mediaTitle.innerHTML = title;
    mediaDesc.innerHTML = `Song &bull; ${game}`;
    // Gemini
    const audioElement = document.querySelector('media-controller [slot="media"]');

    // 2. Assign the new URL path
    audioElement.src = stream;

    // 3. Force the browser to reset and load the new asset
    audioElement.load();

    sendAnalytics("views", songId, 1)
    playingAudioId = songId;

    // 4. (Optional) Initiate playback programmatically
    audioElement.play().catch(error => {
        console.log("Playback blocked until user interaction occurs.");
    });


}
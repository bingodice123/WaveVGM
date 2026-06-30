let playingAudioId = null;
const liked_classes = {true: 'bi-hand-thumbs-up-fill', false: 'bi-hand-thumbs-up'}
let queue = [];
let queue_album = [];

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
    let payload = {}
    if (id === -1) {
        payload = {type, id: playingAudioId, amount};
    } else {
        payload = {type, id, amount};
    }
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
        console.log("page hidden")
        const payload = {type: 'retention_percent', amount: getUniqueListenedStats(audio)["percent"], id: playingAudioId}
        fetch('/api/send-analytics', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
            keepalive: true // Crucial property
        });
    }
});


function endSong() {
    if (queue) {
            console.log(queue)
            playAudio(queue[0].stream, queue[0].imgSrc, queue[0].title, queue[0].game, queue[0].songId, true);
            queue.shift();
        }
}

// Play audio 50% Gemini
function playAudio(stream, imgSrc = 'https://i.imgur.com/x6GQBYz.jpeg', title = 'Unknown', game = 'Unknown', songId, queuePlay) {
    // Me
    if (playingAudioId) {
        sendRetentionPercent()
    }
    if (!queuePlay) {
        queue = [...queue_album];
        const index = queue.findIndex(u => u.songId === songId);
        if (index !== -1) {
            queue.splice(0, index + 1);
        } else {
            // Played from search or top 10 songs, get album data
            
        }
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
    mediaTitle.innerHTML = title.replaceAll("＇", "'").replaceAll("：", ":").replaceAll("＃", "#");
    mediaDesc.innerHTML = `Song &bull; ${game.replaceAll("＇", "'").replaceAll("：", ":").replaceAll("＃", "#")}`;
    // Gemini
    const audioElement = document.querySelector('media-controller [slot="media"]');
    audioElement.removeEventListener('ended', endSong);

    // 2. Assign the new URL path
    audioElement.src = String.raw`${stream.replaceAll("＇", "'").replaceAll("＃", "%23")}`;

    // 3. Force the browser to reset and load the new asset
    audioElement.load();

    sendAnalytics("views", songId, 1)
    playingAudioId = songId;
    const payload = {id: playingAudioId};
    const liked_payload = {id: playingAudioId};
    fetch('/api/update-playing-song', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    }).catch(error => {
        console.error("Error", error);
    });
    fetch('api/has-liked', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(liked_payload)
    }).then((response) => {
    return response.json(); // Returns a new promise
  })
  .then((data) => {
    document.getElementById("like-button").classList.remove("bi-hand-thumbs-up");
    document.getElementById("like-button").classList.remove("bi-hand-thumbs-up-fill");
    document.getElementById("like-button").classList.add(liked_classes[data["liked"]])
  })
    // 4. (Optional) Initiate playback programmatically
    audioElement.play().then(result => {
        audioElement.addEventListener("ended", endSong);
    }).catch(error => {
        console.log("Playback blocked until user interaction occurs.");
    });



}
document.addEventListener("turbo:load", function () {
            fitty('.fit', {minSize: 11, maxSize: 20});
        });

async function getAudioDuration(url) {


  return await new Promise((resolve) => {
      const audio = new Audio(String.raw`${url.replaceAll("＇", "'").replaceAll("＃", "%23")}`);

      audio.addEventListener("loadedmetadata", () => {
              // Optional: Format into minutes and seconds
          const durationInSeconds = audio.duration;
             const minutes = Math.floor(durationInSeconds / 60);
    const seconds = Math.floor(durationInSeconds % 60);
          resolve(`${minutes}:${seconds < 10 ? '0' : ''}${seconds}`);
      }, {once: true});
  });
}

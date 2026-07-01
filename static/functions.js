let playingAudioId = null;
const liked_classes = {true: 'bi-hand-thumbs-up-fill', false: 'bi-hand-thumbs-up'}
let queue = [];
let queueAlbum = [];
let isIndex = false;

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
            playAudio(null, queue[0].stream, queue[0].imgSrc, queue[0].title, queue[0].game, queue[0].songId, true);
            queue.shift();
        }
}

async function getAlbumList(name) {
    try {
        const response = await fetch("/api/get-album-list", {
        method: "post",
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name})
        });
        if (!response.ok) {
            throw new Error(`HTTP Error! Status: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error(`Error: ${error}`);
        throw error;
    }

}

async function disable_dropdown() {
    const disable_toggles = document.querySelectorAll('.disable-toggle');
    const response = await fetch("/api/get-playlist-list", {
        method: "post",
        headers: {"Content-Type": "application/json"}
    });
    const song_id_list = await response.json();
    disable_toggles.forEach((disable_toggle, index) => {
        console.log(`Disable toggle id: ${disable_toggle.dataset.id} song id list ${song_id_list}`)
        if (song_id_list.includes(Number(disable_toggle.dataset.id))) {
            console.log("wow")
            disable_toggle.classList.add("disabled");
            disable_toggle.setAttribute("aria-disabled", "true");
        } else {
            disable_toggle.classList.remove("disabled");
            disable_toggle.setAttribute("aria-disabled", "false");
        }
    });
}


// Play audio 50% Gemini
function playAudio(element, stream, imgSrc = 'https://i.imgur.com/x6GQBYz.jpeg', title = 'Unknown', game = 'Unknown', songId, queuePlay) {
    // Me
    if (playingAudioId) {
        sendRetentionPercent()
    }
    if (!queuePlay) {
        if (queueAlbum.length !== 0 && !isIndex) {
            queue = [...queueAlbum];
            const index = queue.findIndex(u => u.songId === songId);
            if (index !== -1) {
                queue.splice(0, index + 1);
            }
        } else {
            getAlbumList(element.dataset.albumName).then((result) => {
                console.log(result);
                queue = result.list;
                console.log(queue);
                console.log(songId);
                const index = queue.findIndex(u => Number(u.songId) === Number(songId));
                console.log(index);
                if (index !== -1) {
                    queue.splice(0, index + 1);
                }
            });
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
    mediaTitle.innerHTML = title.replaceAll("＇", "'").replaceAll("：", ":").replaceAll("＃", "#").replaceAll("⧸", "/");
    mediaDesc.innerHTML = `Song &bull; ${game.replaceAll("＇", "'").replaceAll("：", ":").replaceAll("＃", "#")}`;
    // Gemini
    const audioElement = document.querySelector('media-controller [slot="media"]');
    audioElement.removeEventListener('ended', endSong);

    // 2. Assign the new URL path
    audioElement.src = String.raw`${stream.replaceAll("＇", "'").replaceAll("＃", "%23")}`;

    // 3. Force the browser to reset and load the new asset
    audioElement.load();
    const links = document.querySelectorAll('.add-to-playlist');
    links.forEach((link, index) => {
        const url = new URL(link.href);
        url.searchParams.set('songId', songId.toString());
        link.href = url.toString();
    });

    sendAnalytics("views", songId, 1);
    playingAudioId = songId;
    const payload = {id: playingAudioId};
    const liked_payload = {id: playingAudioId};
    fetch('/api/update-playing-song', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    }).then((result) => {
        disable_dropdown();
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
  });

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

document.addEventListener("turbo:load", function () {
    isIndex = window.location.pathname === "/"
});


document.addEventListener("click", function (event) {
    const button = event.target.closest('#media-controls [data-bs-toggle="dropdown"]');
  if (!button) return;

  event.preventDefault();
  event.stopImmediatePropagation();

  if (!window.bootstrap?.Dropdown) {
    console.error("Bootstrap Dropdown is not loaded yet");
    return;
  }
  bootstrap.Dropdown.getOrCreateInstance(button).toggle();
}, true);

document.addEventListener("turbo:load", disable_dropdown);
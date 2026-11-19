function mediaErrorMessage(error, label) {
  switch (error.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Quyền ' + label + ' bị chặn. Mở report.html trực tiếp trong Safari hoặc Chrome và kiểm tra quyền của trang và trình duyệt trong Quyền riêng tư & Bảo mật trên macOS.';
    case 'NotFoundError':
      return 'Trình duyệt không tìm thấy ' + label + '. Kiểm tra thiết bị đầu vào trên macOS rồi thử lại.';
    case 'NotReadableError':
    case 'AbortError':
      return 'Không mở được ' + label + '. Đóng ứng dụng đang dùng thiết bị rồi thử lại.';
    default:
      return 'Không khởi động được ' + label + ' (' + error.name + ').';
  }
}

function setupMediaTest(buttonId, statusId, kind, label) {
  const button = document.getElementById(buttonId);
  const status = document.getElementById(statusId);
  const video = document.getElementById('preview');
  const meter = document.getElementById('micLevel');
  let stream = null;
  let audioContext = null;
  let frame = null;
  let request = 0;

  function stop(message) {
    request++;
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (frame !== null) cancelAnimationFrame(frame);
    if (audioContext) audioContext.close().catch(() => {});
    stream = null;
    audioContext = null;
    frame = null;
    if (kind === 'video') {
      video.srcObject = null;
      video.hidden = true;
    } else {
      meter.style.width = '0';
    }
    button.textContent = 'Bật ' + label;
    button.disabled = false;
    status.textContent = message;
  }

  button.onclick = async function () {
    if (stream) {
      stop('Đã tắt ' + label + '.');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'Chế độ xem này không hỗ trợ ' + label + '. Mở tệp report.html trực tiếp trong Safari hoặc Chrome.';
      return;
    }
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (kind === 'audio' && !AudioContextType) {
      status.textContent = 'Trình duyệt không hỗ trợ đo mức âm. Hãy mở báo cáo trong Safari hoặc Chrome.';
      return;
    }

    const id = ++request;
    button.disabled = true;
    status.textContent = 'Đang mở ' + label + '…';
    try {
      if (kind === 'audio') {
        audioContext = new AudioContextType();
        audioContext.resume().catch(() => {});
      }
      const input = await navigator.mediaDevices.getUserMedia({ [kind]: true });
      if (id !== request) {
        input.getTracks().forEach(track => track.stop());
        return;
      }
      stream = input;
      stream.getTracks().forEach(track => track.addEventListener('ended', () => {
        if (id === request) stop('Đã ngắt kết nối ' + label + '.');
      }));
      if (kind === 'video') {
        video.srcObject = stream;
        video.hidden = false;
        await video.play();
      } else {
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 256;
        audioContext.createMediaStreamSource(stream).connect(analyser);
        const values = new Uint8Array(analyser.frequencyBinCount);
        function draw() {
          analyser.getByteFrequencyData(values);
          meter.style.width = (Math.max(...values) / 2.55) + '%';
          frame = requestAnimationFrame(draw);
        }
        draw();
      }
      if (id !== request) return;
      status.textContent = 'Đang bật ' + label + '.';
      button.textContent = 'Tắt ' + label;
      button.disabled = false;
    } catch (error) {
      if (id === request) stop(mediaErrorMessage(error, label));
    }
  };
  window.addEventListener('pagehide', () => stop(''));
}

setupMediaTest('cameraButton', 'cameraStatus', 'video', 'camera');
setupMediaTest('micButton', 'micStatus', 'audio', 'micro');

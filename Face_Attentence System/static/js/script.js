document.addEventListener('DOMContentLoaded', () => {
    // Audio Context
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

    function beep(freq = 520, duration = 200, type = 'sine') {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = type;
        osc.frequency.value = freq;
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + duration / 1000);
        osc.stop(audioCtx.currentTime + duration / 1000);
    }

    // Global Click Sound
    document.querySelectorAll('a, button').forEach(el => {
        el.addEventListener('click', () => {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            beep(800, 50, 'triangle');
        });
    });

    // Sidebar Toggle Logic Removed (Navigation moved to Top Header)
});


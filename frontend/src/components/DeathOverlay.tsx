import './DeathOverlay.css';

interface DeathOverlayProps {
  intensity?: 'light' | 'full';
}

const LIGHT_BLOBS = [
  { width: 400, height: 160, bottom: '-30px', left: '5%',   delay: '0s',   duration: '30s', variant: 'la' },
  { width: 350, height: 140, bottom: '-25px', left: '45%',  delay: '4s',   duration: '34s', variant: 'lb' },
  { width: 380, height: 150, bottom: '-35px', left: '75%',  delay: '2s',   duration: '32s', variant: 'lc' },
  { width: 300, height: 280, top: '40%',  left: '-40px',     delay: '6s',   duration: '36s', variant: 'lb' },
  { width: 320, height: 260, top: '30%',  right: '-40px',    delay: '8s',   duration: '33s', variant: 'lc' },
];

const FULL_BLOBS = [
  { width: 450, height: 180, bottom: '-35px', left: '0%',    delay: '0s',   duration: '26s', variant: 'fa' },
  { width: 500, height: 200, bottom: '-40px', left: '20%',   delay: '2.5s', duration: '30s', variant: 'fb' },
  { width: 420, height: 170, bottom: '-30px', left: '45%',   delay: '1s',   duration: '24s', variant: 'fc' },
  { width: 480, height: 190, bottom: '-38px', left: '65%',   delay: '4s',   duration: '28s', variant: 'fd' },
  { width: 400, height: 175, bottom: '-32px', left: '85%',   delay: '3s',   duration: '32s', variant: 'fa' },
  { width: 380, height: 320, top: '25%',  left: '-50px',     delay: '5s',   duration: '34s', variant: 'fb' },
  { width: 350, height: 300, top: '50%',  left: '-45px',     delay: '9s',   duration: '30s', variant: 'fc' },
  { width: 400, height: 310, top: '20%',  right: '-50px',    delay: '7s',   duration: '32s', variant: 'fd' },
  { width: 440, height: 340, top: '10%',  left: '30%',       delay: '6s',   duration: '35s', variant: 'fa' },
  { width: 380, height: 300, top: '45%',  left: '55%',       delay: '11s',  duration: '29s', variant: 'fb' },
];

function DeathOverlay({ intensity = 'light' }: DeathOverlayProps) {
  const isFull = intensity === 'full';
  const blobs = isFull ? FULL_BLOBS : LIGHT_BLOBS;

  return (
    <div className={`death-overlay${isFull ? ' death-overlay--full' : ''}`}>
      {isFull && <div className="death-tint" />}
      <div className="death-smoke">
        {isFull && <div className="death-smoke-base" />}
        {blobs.map((b, i) => (
          <div
            key={i}
            className={`death-smoke-blob ${b.variant}`}
            style={{
              width: b.width,
              height: b.height,
              top: b.top,
              bottom: b.bottom,
              left: b.left,
              right: b.right,
              '--duration': b.duration,
              '--delay': b.delay,
            } as React.CSSProperties}
          />
        ))}
      </div>
    </div>
  );
}

export default DeathOverlay;

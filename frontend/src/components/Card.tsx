import './Card.css';

interface CardProps {
  image?: string;
  burning?: boolean;
  burnSide?: 'left' | 'right' | 'center';
  appearing?: boolean;
  onClick?: () => void;
}

function Card({
  image,
  burning = false,
  burnSide = 'center',
  appearing = false,
  onClick,
}: CardProps) {
  const sideClass = burning ? ` card-burn-${burnSide}` : '';

  return (
    <div
      className={`card${burning ? ' is-burning' : ''}${sideClass}${appearing ? ' is-appearing' : ''}`}
      style={image ? { backgroundImage: `url(${image})` } : undefined}
      onClick={onClick}
    />
  );
}

export default Card;

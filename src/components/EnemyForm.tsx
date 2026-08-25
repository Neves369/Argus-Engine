function EnemyForm() {
  return (
    <form className="modal-form">
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-name">
          Nome
        </label>
        <input className="modal-input" id="enemy-name" type="text" />
      </div>
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-health">
          Vida
        </label>
        <input className="modal-input" id="enemy-health" type="number" />
      </div>
      <div className="modal-field">
        <label className="modal-label" htmlFor="enemy-mana">
          Mana
        </label>
        <input className="modal-input" id="enemy-mana" type="number" />
      </div>
      <button className="modal-submit" type="submit">
        Salvar
      </button>
    </form>
  );
}

export default EnemyForm;

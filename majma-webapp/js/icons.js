// Linien-Icons im Stil des Designs (24×24, abgerundete Striche).

const paths = {
  home: 'M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-4v-6h-6v6H5a1 1 0 0 1-1-1z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  feed: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7',
  message: 'M4 5h16v11H8l-4 4z',
  heart: 'M12 21s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.5-7 10-7 10z',
  school: 'M3 8l9-4 9 4-9 4zM7 10v5c3 2 7 2 10 0v-5',
  family: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM3 20a5 5 0 0 1 10 0M13 20a4 4 0 0 1 8 0',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
  mosque: 'M12 3c-3 3-6 5-6 9v8h12v-8c0-4-3-6-6-9zM12 16h.01',
  card: 'M3 6h18v12H3zM3 10h18M7 15h4',
  bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0',
  calendar: 'M4 6h16v14H4zM4 10h16M8 3v4M16 3v4',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM20 20l-4-4',
  back: 'M15 5l-7 7 7 7',
  next: 'M9 5l7 7-7 7',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  menu: 'M4 7h16M4 12h16M4 17h16',
  close: 'M6 6l12 12M18 6L6 18',
  phone: 'M8 2h8a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM11 18h2',
  mail: 'M3 6h18v12H3zM3 7l9 6 9-6',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  expand: 'M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5',
  rug: 'M5 5h14v14H5zM8 9h8M8 12h8M8 15h8',
  flame: 'M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-1 3-3 4-3 4s-1-2-1-4c-2 2-4 5-4 10a6 6 0 0 0 6 6z',
  book: 'M4 18l8-12 8 12M7 14h10',
  bottle: 'M10 3h4v4l2 3v11H8V10l2-3zM8 13h8',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c1 1 1 2 1 2.5h6c0-.5 0-1.5 1-2.5A6 6 0 0 0 12 3z',
  logout: 'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
};

export function icon(name, { size = 24, stroke = 'currentColor', width = 1.7 } = {}) {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name]}"></path></svg>`;
}

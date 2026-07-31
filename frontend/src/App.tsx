import { BrowserRouter, Route, Routes } from 'react-router-dom';
import CalendarPage from './CalendarPage';
import EditionPage, { RootRedirect, StatusScreen } from './EditionPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/d/:date" element={<EditionPage />} />
        <Route path="/calendar" element={<CalendarPage />} />
        <Route path="*" element={<StatusScreen>존재하지 않는 페이지입니다.</StatusScreen>} />
      </Routes>
    </BrowserRouter>
  );
}

function Footer({ layoutClass = "" }: { layoutClass?: string }) {
  return (
    <footer className={`shadow-sm bg-gray-800 ${layoutClass}`}>
      <div className="flex justify-center w-full max-w-screen-xl p-4 mx-auto">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          © 2025 JY™. All Rights Reserved.
        </span>
      </div>
    </footer>
  );
}

export default Footer;

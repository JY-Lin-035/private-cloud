import { useEffect, useMemo, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { useStorage } from '../../store/storage';



function Dashboard() {
  const storage = useStorage();
  const [chartData, setChartData] = useState<any[]>([]);

  const used = useMemo(() => storage.format(storage.usedStorage), [storage.usedStorage]);
  const usedGB = useMemo(() => storage.format(storage.usedStorage, "GB"), [storage.usedStorage]);
  const available = useMemo(() => storage.format(storage.availableStorage), [storage.availableStorage]);
  const availableGB = useMemo(() => storage.format(storage.availableStorage, "GB"), [storage.availableStorage]);
  const percentage = useMemo(() => storage.percentage, [storage.percentage]);

  useEffect(() => {
    const data = storage.loadFromLocalStorage();

    if (!data) {
      storage.getFromAPI();
    }
  }, []);

  useEffect(() => {
    setChartData([
      { name: `${used[0]} ${used[1]} Used`, value: usedGB[0], color: '#E74694' },
      { name: `${available[0]} ${available[1]} Available`, value: availableGB[0], color: '#16BDCA' },
    ]);
  }, [used, available, usedGB, availableGB]);

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white p-2 rounded shadow">
          <p className="text-sm">{`${payload[0].name}`}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="py-6">
      <ResponsiveContainer width="100%" height={200}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
          <Legend 
            verticalAlign="bottom" 
            height={36}
            formatter={(value: string) => <span className="text-white">{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="text-center text-white text-2xl font-bold mt-4">
        {Number(percentage)}%
      </div>
    </div>
  );
}

export default Dashboard;

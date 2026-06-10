import { useEffect, useMemo, useState } from 'react';
import ReactApexChart from 'react-apexcharts';
import { useStorage } from '../../store/storage';



function Dashboard({ layoutClass }: { layoutClass: string }) {
  const storage = useStorage();
  const [chartOptions, setChartOptions] = useState<any>({});
  const [chartSeries, setChartSeries] = useState<number[]>([]);

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
    setChartSeries([usedGB[0], availableGB[0]]);
    setChartOptions({
      series: [usedGB[0], availableGB[0]],
      colors: ['#E74694', '#16BDCA'],
      chart: {
        height: '100%',
        width: '100%',
        type: 'donut',
        animations: {
          enabled: true,
          easing: 'easeinout',
          speed: 350,
          animateGradually: {
            enabled: true,
            delay: 100,
          },
        },
      },
      states: {
        active: {
          allowMultipleDataPointsSelection: false,
          filter: {
            type: 'none',
          },
        },
      },
      stroke: {
        colors: ['transparent'],
        lineCap: '',
      },
      plotOptions: {
        pie: {
          donut: {
            labels: {
              show: true,
              name: {
                show: true,
                fontFamily: 'Inter, sans-serif',
                fontSize: '100%',
                color: 'white',
                offsetY: 100,
              },
              total: {
                showAlways: true,
                show: true,
                label: '',
                fontFamily: 'Inter, sans-serif',
                fontSize: '100%',
                color: 'white',
                fontWeight: 'bold',
                formatter: function (_w: any) {
                  return `${Number(percentage)} %`;
                },
              },
              value: {
                show: true,
                fontFamily: 'Inter, sans-serif',
                fontSize: '100%',
                color: 'white',
                offsetY: 0,
                formatter: function (_w: any) {
                  return `${Number(percentage)} %`;
                },
              },
            },
            size: '70%',
          },
        },
      },
      grid: {
        padding: {
          top: -2,
        },
      },
      tooltip: {
        y: {
          formatter: function (val: number) {
            const value = val === usedGB[0] ? used : available;
            return `${value[0]} ${value[1]}`;
          },
          title: {
            formatter: function () {
              return '';
            },
          },
        },
      },
      labels: [
        `${used[0]} ${used[1]} Used`,
        `${available[0]} ${available[1]} Available`,
      ],
      dataLabels: {
        enabled: false,
      },
      legend: {
        position: 'bottom',
        fontFamily: 'Inter, sans-serif',
        fontSize: '1rem',
        labels: {
          colors: ['white', 'white'],
        },
      },
      yaxis: {
        labels: {
          formatter: function () {
            return '';
          },
        },
      },
      xaxis: {
        labels: {
          formatter: function (value: string) {
            return value;
          },
        },
        axisTicks: {
          show: false,
        },
        axisBorder: {
          show: false,
        },
      },
    });
  }, [used, available, usedGB, availableGB, percentage]);

  return (
    <>
      <style>{`
        .apexcharts-legend-text {
          color: white !important;
          margin-left: -10px !important;
          margin-right: 15px !important;
        }
      `}</style>
      <div className={`py-6 h-[35vh] ${layoutClass}`} id="donut-chart">
        <ReactApexChart
          options={chartOptions}
          series={chartSeries}
          type="donut"
          height="75%"
        />
      </div>
    </>
  );
}

export default Dashboard;
